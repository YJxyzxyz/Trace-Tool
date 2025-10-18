"""Call tree data structures used by the tracer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional


def _format_location(filename: Optional[str], lineno: int) -> str:
    if not filename:
        return ""
    return f"{filename}:{lineno}" if lineno else filename


@dataclass
class CallTreeNode:
    """Represents a single node in the call tree."""

    function: str
    filename: Optional[str]
    lineno: int
    total_time: float = 0.0
    self_time: float = 0.0
    call_count: int = 0
    children: List["CallTreeNode"] = field(default_factory=list)
    parent: Optional["CallTreeNode"] = field(default=None, repr=False)

    def add_child(self, node: "CallTreeNode") -> None:
        node.parent = self
        self.children.append(node)

    @property
    def location(self) -> str:
        return _format_location(self.filename, self.lineno)

    def to_dict(self) -> dict:
        return {
            "function": self.function,
            "filename": self.filename,
            "lineno": self.lineno,
            "total_time": self.total_time,
            "self_time": self.self_time,
            "call_count": self.call_count,
            "children": [child.to_dict() for child in self.children],
        }

    def iter_depth_first(self) -> Iterable["CallTreeNode"]:
        yield self
        for child in self.children:
            yield from child.iter_depth_first()

    def format_branch(self) -> str:
        location = self.location
        if location:
            return f"{self.function} ({location})"
        return self.function

    def is_root(self) -> bool:
        return self.parent is None
