"""Visualization helpers for tracer output."""
from __future__ import annotations

from typing import Iterable, List, Optional

from .call_tree import CallTreeNode


def _iter_visible_children(node: CallTreeNode, max_depth: Optional[int], depth: int) -> Iterable[CallTreeNode]:
    if max_depth is not None and depth >= max_depth:
        return []
    return node.children


def render_ascii_tree(root: CallTreeNode, max_depth: Optional[int] = None) -> str:
    """Return an ASCII representation of the call tree."""

    lines: List[str] = []

    def walk(node: CallTreeNode, prefix: str, is_last: bool, depth: int) -> None:
        connector = "└── " if is_last else "├── "
        branch = node.format_branch()
        if not node.is_root():
            lines.append(
                f"{prefix}{connector}{branch} "
                f"[calls={node.call_count}, total={node.total_time:.6f}s, self={node.self_time:.6f}s]"
            )
        child_prefix = prefix + ("    " if is_last else "│   ")
        children = list(_iter_visible_children(node, max_depth, depth))
        for index, child in enumerate(children):
            walk(child, child_prefix, index == len(children) - 1, depth + 1)

    walk(root, "", True, 0)
    return "\n".join(lines)


def to_dot(root: CallTreeNode, max_depth: Optional[int] = None) -> str:
    """Return a Graphviz DOT representation of the call tree."""

    lines = ["digraph CallTree {", "  node [shape=box, style=rounded];"]
    index_map = {}

    def node_id(node: CallTreeNode) -> str:
        if node not in index_map:
            index_map[node] = f"n{len(index_map)}"
        return index_map[node]

    def label(node: CallTreeNode) -> str:
        location = node.location
        metrics = f"\\ncalls={node.call_count}\\ntotal={node.total_time:.6f}s\\nself={node.self_time:.6f}s"
        if location:
            return f"{node.function}\\n{location}{metrics}"
        return f"{node.function}{metrics}"

    def walk(node: CallTreeNode, depth: int) -> None:
        lines.append(f"  {node_id(node)} [label=\"{label(node)}\"]; ")
        if max_depth is not None and depth >= max_depth:
            return
        for child in node.children:
            lines.append(f"  {node_id(node)} -> {node_id(child)};")
            walk(child, depth + 1)

    walk(root, 0)
    lines.append("}")
    return "\n".join(lines)
