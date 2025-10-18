"""Core tracing logic for Python execution."""
from __future__ import annotations

import linecache
import os
import runpy
import sys
import threading
import time
from dataclasses import dataclass
from types import FrameType
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .call_tree import CallTreeNode


@dataclass
class LineEvent:
    """Information about a line execution event."""

    timestamp: float
    filename: str
    lineno: int
    function: str
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "filename": self.filename,
            "lineno": self.lineno,
            "function": self.function,
            "source": self.source,
        }


@dataclass
class FunctionStats:
    """Aggregated statistics for a function."""

    filename: str
    function: str
    lineno: int
    call_count: int = 0
    total_time: float = 0.0
    self_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "function": self.function,
            "lineno": self.lineno,
            "call_count": self.call_count,
            "total_time": self.total_time,
            "self_time": self.self_time,
        }


@dataclass
class TraceResult:
    """Container for the collected trace information."""

    call_events: List[dict]
    line_events: List[LineEvent]
    function_stats: Dict[Tuple[str, str, int], FunctionStats]
    call_tree: CallTreeNode
    total_time: float

    def to_dict(self) -> dict:
        return {
            "total_time": self.total_time,
            "call_events": list(self.call_events),
            "line_events": [event.to_dict() for event in self.line_events],
            "function_stats": [stats.to_dict() for stats in self.function_stats.values()],
            "call_tree": self.call_tree.to_dict(),
        }

    def sorted_functions(self, sort_by: str = "total_time", reverse: bool = True) -> List[FunctionStats]:
        if sort_by not in {"total_time", "self_time", "call_count"}:
            raise ValueError("sort_by must be one of 'total_time', 'self_time', or 'call_count'")
        return sorted(self.function_stats.values(), key=lambda s: getattr(s, sort_by), reverse=reverse)


@dataclass
class _FrameState:
    node: CallTreeNode
    start_time: float
    child_time: float = 0.0


def _safe_repr(value: object, limit: int = 120) -> str:
    try:
        text = repr(value)
    except Exception:
        text = object.__repr__(value)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


class Tracer:
    """Trace Python execution and collect timing information."""

    def __init__(
        self,
        *,
        root: Optional[str] = None,
        include_stdlib: bool = False,
        capture_sources: bool = True,
    ) -> None:
        self.root = os.path.abspath(root) if root else None
        self.include_stdlib = include_stdlib
        self.capture_sources = capture_sources
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        self._call_events: List[dict] = []
        self._line_events: List[LineEvent] = []
        self._function_stats: Dict[Tuple[str, str, int], FunctionStats] = {}
        self._call_stack: Dict[int, List[_FrameState]] = {}
        self._root_node = CallTreeNode("<root>", None, 0)
        self._active = False
        self._start_clock = 0.0
        self._stop_clock = 0.0

    def _current_stack(self) -> List[_FrameState]:
        thread_id = threading.get_ident()
        return self._call_stack.setdefault(thread_id, [])

    def _trace(self, frame: FrameType, event: str, arg: object) -> Optional[Callable]:
        if event not in {"call", "line", "return"}:
            return self._trace

        code = frame.f_code
        filename = os.path.abspath(code.co_filename)
        if not self._should_trace(filename):
            return self._trace

        function = code.co_name
        definition_line = code.co_firstlineno
        thread_id = threading.get_ident()
        timestamp = time.perf_counter() - self._start_clock

        if event == "call":
            return self._handle_call(thread_id, filename, definition_line, function, timestamp)
        if event == "line":
            return self._handle_line(frame, filename, function, timestamp)
        if event == "return":
            return self._handle_return(thread_id, filename, definition_line, function, timestamp, arg)
        return self._trace

    def _handle_call(
        self,
        thread_id: int,
        filename: str,
        lineno: int,
        function: str,
        timestamp: float,
    ) -> Callable:
        stack = self._call_stack.setdefault(thread_id, [])
        node = CallTreeNode(function, filename, lineno)
        if stack:
            stack[-1].node.add_child(node)
        else:
            self._root_node.add_child(node)
        frame_state = _FrameState(node=node, start_time=time.perf_counter())
        stack.append(frame_state)
        self._call_events.append(
            {
                "timestamp": timestamp,
                "thread_id": thread_id,
                "event": "call",
                "function": function,
                "filename": filename,
                "lineno": lineno,
            }
        )
        return self._trace

    def _handle_line(
        self,
        frame: FrameType,
        filename: str,
        function: str,
        timestamp: float,
    ) -> Callable:
        stack = self._current_stack()
        if not stack:
            return self._trace
        lineno = frame.f_lineno
        source = None
        if self.capture_sources:
            source = linecache.getline(filename, lineno).rstrip() or None
        self._line_events.append(
            LineEvent(
                timestamp=timestamp,
                filename=filename,
                lineno=lineno,
                function=function,
                source=source,
            )
        )
        return self._trace

    def _handle_return(
        self,
        thread_id: int,
        filename: str,
        lineno: int,
        function: str,
        timestamp: float,
        return_value: object,
    ) -> Callable:
        stack = self._call_stack.get(thread_id)
        if not stack:
            return self._trace
        frame_state = stack.pop()
        end_time = time.perf_counter()
        duration = end_time - frame_state.start_time
        self_time = duration - frame_state.child_time
        key = (filename, function, lineno)
        stats = self._function_stats.get(key)
        if stats is None:
            stats = FunctionStats(filename=filename, function=function, lineno=lineno)
            self._function_stats[key] = stats
        stats.call_count += 1
        stats.total_time += duration
        stats.self_time += max(self_time, 0.0)

        frame_state.node.call_count += 1
        frame_state.node.total_time += duration
        frame_state.node.self_time += max(self_time, 0.0)

        if stack:
            stack[-1].child_time += duration

        self._call_events.append(
            {
                "timestamp": timestamp,
                "thread_id": thread_id,
                "event": "return",
                "function": function,
                "filename": filename,
                "lineno": lineno,
                "return_value": _safe_repr(return_value),
            }
        )
        return self._trace

    def _should_trace(self, filename: str) -> bool:
        if self.include_stdlib:
            return True
        if self.root and filename.startswith(self.root):
            return True
        cwd = os.getcwd()
        return filename.startswith(cwd)

    def start(self) -> None:
        with self._lock:
            if self._active:
                raise RuntimeError("Tracer already running")
            self.reset()
            self._active = True
            self._start_clock = time.perf_counter()
            sys.settrace(self._trace)
            threading.settrace(self._trace)

    def stop(self) -> TraceResult:
        with self._lock:
            if not self._active:
                raise RuntimeError("Tracer is not running")
            sys.settrace(None)
            threading.settrace(None)
            self._stop_clock = time.perf_counter()
            self._active = False
            return TraceResult(
                call_events=self._call_events,
                line_events=self._line_events,
                function_stats=self._function_stats,
                call_tree=self._root_node,
                total_time=self._stop_clock - self._start_clock,
            )

    def runfunc(self, func: Callable, *args, **kwargs) -> TraceResult:
        result: Optional[TraceResult] = None
        self.start()
        try:
            func(*args, **kwargs)
        finally:
            result = self.stop()
        if result is None:
            raise RuntimeError("Trace result was not collected")
        return result

    def run_script(self, script_path: str, argv: Optional[List[str]] = None) -> TraceResult:
        script_abspath = os.path.abspath(script_path)
        previous_root = self.root
        self.root = self.root or os.path.dirname(script_abspath)
        argv = list(argv) if argv is not None else [script_abspath]
        old_argv = sys.argv
        result: Optional[TraceResult] = None
        try:
            self.start()
            sys.argv = argv
            try:
                runpy.run_path(script_abspath, run_name="__main__")
            finally:
                result = self.stop()
        finally:
            sys.argv = old_argv
            if previous_root is None:
                self.root = None
        if result is None:
            raise RuntimeError("Trace result was not collected")
        return result

    def trace(self, func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            self.start()
            try:
                return func(*args, **kwargs)
            finally:
                self.stop()

        return wrapper

    def collect(self) -> TraceResult:
        if self._active:
            raise RuntimeError("Tracer is currently running")
        return TraceResult(
            call_events=self._call_events,
            line_events=self._line_events,
            function_stats=self._function_stats,
            call_tree=self._root_node,
            total_time=self._stop_clock - self._start_clock,
        )

    @staticmethod
    def format_stats(functions: Iterable[FunctionStats], limit: int = 10) -> str:
        rows = ["Function", "Calls", "Total(s)", "Self(s)"]
        header = f"{rows[0]:60} {rows[1]:>8} {rows[2]:>12} {rows[3]:>12}"
        lines = [header, "-" * len(header)]
        for stats in list(functions)[:limit]:
            location = f"{stats.filename}:{stats.lineno}"
            label = f"{stats.function} ({location})"
            lines.append(
                f"{label:60.60} {stats.call_count:>8} {stats.total_time:>12.6f} {stats.self_time:>12.6f}"
            )
        return "\n".join(lines)
