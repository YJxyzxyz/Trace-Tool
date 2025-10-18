"""Command line interface for the Python execution tracer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

from tracer import Tracer
from tracer.visualization import render_ascii_tree, to_dot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Trace the execution of a Python script and collect timing information.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("script", help="Path to the Python script to trace.")
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the traced script (prefix with -- to avoid confusion with tracer options).",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Only trace files located under this directory.",
    )
    parser.add_argument(
        "--include-stdlib",
        action="store_true",
        help="Include files from the Python standard library in the trace output.",
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Do not capture the source code for line execution events.",
    )
    parser.add_argument(
        "--sort-by",
        choices=["total_time", "self_time", "call_count"],
        default="total_time",
        help="Metric used to sort function statistics.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of functions to display in the performance summary.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum depth of the call tree shown in the console output.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=20,
        help="Maximum number of executed lines to display in the console output.",
    )
    parser.add_argument(
        "--dot",
        type=Path,
        help="Path where a Graphviz DOT representation of the call tree will be written.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Path where the full trace information will be written as JSON.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    script_path = Path(args.script).resolve()
    if not script_path.exists():
        parser.error(f"Script not found: {script_path}")

    tracer = Tracer(
        root=os.path.abspath(args.root) if args.root else None,
        include_stdlib=args.include_stdlib,
        capture_sources=not args.no_source,
    )

    script_args = [str(script_path)] + list(args.script_args or [])
    result = tracer.run_script(str(script_path), argv=script_args)

    print(f"\nExecution finished in {result.total_time:.6f} seconds\n")
    stats = result.sorted_functions(sort_by=args.sort_by)
    print("Top functions:")
    print(Tracer.format_stats(stats, limit=args.top))

    print("\nCall tree:")
    print(render_ascii_tree(result.call_tree, max_depth=args.max_depth))

    if args.max_lines:
        print("\nLine execution events:")
        for event in result.line_events[: args.max_lines]:
            source = f" -> {event.source}" if event.source else ""
            print(f"[{event.timestamp:>10.6f}s] {event.filename}:{event.lineno} in {event.function}{source}")
        if len(result.line_events) > args.max_lines:
            print(f"... ({len(result.line_events) - args.max_lines} more events)")

    if args.dot:
        dot_content = to_dot(result.call_tree, max_depth=args.max_depth)
        args.dot.write_text(dot_content, encoding="utf-8")
        print(f"\nDOT call tree written to {args.dot}")

    if args.json:
        args.json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"Trace data exported to {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
