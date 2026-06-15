"""Non-destructive rectangle-tree layout model.

The Blender PropertyGroup storage mirrors these records, but this module stays
pure Python so tests and future command-line tools can validate layouts without
loading Blender.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ..constants import SPLIT_HORIZONTAL, SPLIT_NONE, SPLIT_VERTICAL

Color = tuple[float, float, float, float]


@dataclass(frozen=True)
class Bounds:
    x0: float
    y0: float
    x1: float
    y1: float

    def validate(self) -> None:
        if not (0.0 <= self.x0 <= self.x1 <= 1.0 and 0.0 <= self.y0 <= self.y1 <= 1.0):
            raise ValueError(f"Bounds must stay inside normalized UV space: {self!r}")
        if self.x0 == self.x1 or self.y0 == self.y1:
            raise ValueError(f"Bounds must have positive area: {self!r}")


@dataclass(frozen=True)
class NodeRecord:
    node_id: int
    parent_id: int
    child_index: int
    split_kind: str = SPLIT_NONE
    split_ratio: float = 0.5
    color: Color = (1.0, 1.0, 1.0, 1.0)
    label: str = ""


@dataclass(frozen=True)
class LeafRegion:
    node_id: int
    bounds: Bounds
    color: Color
    label: str


def build_root(color: Color = (1.0, 1.0, 1.0, 1.0), label: str = "Region 1") -> list[NodeRecord]:
    return [
        NodeRecord(
            node_id=1,
            parent_id=-1,
            child_index=0,
            split_kind=SPLIT_NONE,
            split_ratio=0.5,
            color=color,
            label=label,
        )
    ]


def find_node(nodes: Sequence[NodeRecord], node_id: int) -> NodeRecord | None:
    return next((node for node in nodes if node.node_id == node_id), None)


def next_node_id(nodes: Sequence[NodeRecord]) -> int:
    return max((node.node_id for node in nodes), default=0) + 1


def children_of(nodes: Sequence[NodeRecord], parent_id: int) -> list[NodeRecord]:
    return sorted(
        (node for node in nodes if node.parent_id == parent_id),
        key=lambda node: node.child_index,
    )


def is_leaf(nodes: Sequence[NodeRecord], node_id: int) -> bool:
    node = find_node(nodes, node_id)
    if node is None:
        raise ValueError(f"Unknown node id: {node_id}")
    return len(children_of(nodes, node_id)) == 0


def split_node(
    nodes: Sequence[NodeRecord],
    node_id: int,
    orientation: str,
    ratio: float = 0.5,
) -> list[NodeRecord]:
    if orientation not in {SPLIT_HORIZONTAL, SPLIT_VERTICAL}:
        raise ValueError(f"Unsupported split orientation: {orientation}")
    if not 0.001 <= ratio <= 0.999:
        raise ValueError("Split ratio must be between 0.001 and 0.999")

    target = find_node(nodes, node_id)
    if target is None:
        raise ValueError(f"Unknown node id: {node_id}")
    if not is_leaf(nodes, node_id):
        raise ValueError("Only leaf regions can be split")

    first_id = next_node_id(nodes)
    updated: list[NodeRecord] = []
    for node in nodes:
        if node.node_id == node_id:
            updated.append(replace(node, split_kind=orientation, split_ratio=ratio))
        else:
            updated.append(node)

    updated.extend(
        [
            NodeRecord(
                node_id=first_id,
                parent_id=node_id,
                child_index=0,
                split_kind=SPLIT_NONE,
                split_ratio=0.5,
                color=target.color,
                label=f"Region {first_id}",
            ),
            NodeRecord(
                node_id=first_id + 1,
                parent_id=node_id,
                child_index=1,
                split_kind=SPLIT_NONE,
                split_ratio=0.5,
                color=target.color,
                label=f"Region {first_id + 1}",
            ),
        ]
    )
    return updated


def validate_grid_dimensions(rows: int, columns: int, max_size: int = 16) -> None:
    if not 1 <= rows <= max_size:
        raise ValueError(f"Rows must be between 1 and {max_size}")
    if not 1 <= columns <= max_size:
        raise ValueError(f"Columns must be between 1 and {max_size}")
    if rows == 1 and columns == 1:
        raise ValueError("Grid subdivision must create at least two cells")


def _split_into_equal_segments(
    nodes: Sequence[NodeRecord],
    node_id: int,
    orientation: str,
    count: int,
) -> tuple[list[NodeRecord], list[int]]:
    if count < 1:
        raise ValueError("Segment count must be at least 1")
    if count == 1:
        return list(nodes), [node_id]

    updated = list(nodes)
    segment_ids: list[int] = []
    current_id = node_id
    for remaining in range(count, 1, -1):
        first_child_id = next_node_id(updated)
        updated = split_node(updated, current_id, orientation, 1.0 / remaining)
        segment_ids.append(first_child_id)
        current_id = first_child_id + 1
    segment_ids.append(current_id)
    return updated, segment_ids


def grid_subdivide_node(
    nodes: Sequence[NodeRecord],
    node_id: int,
    rows: int,
    columns: int,
) -> tuple[list[NodeRecord], list[int]]:
    validate_grid_dimensions(rows, columns)
    if not is_leaf(nodes, node_id):
        raise ValueError("Only leaf regions can be grid subdivided")

    updated, row_ids = _split_into_equal_segments(nodes, node_id, SPLIT_HORIZONTAL, rows)
    cell_ids: list[int] = []
    for row_id in row_ids:
        updated, column_ids = _split_into_equal_segments(updated, row_id, SPLIT_VERTICAL, columns)
        cell_ids.extend(column_ids)
    return updated, cell_ids


def derive_leaf_regions(
    nodes: Sequence[NodeRecord],
    root_bounds: Bounds = Bounds(0.0, 0.0, 1.0, 1.0),
) -> list[LeafRegion]:
    if not nodes:
        return []

    root = next((node for node in nodes if node.parent_id == -1), None)
    if root is None:
        raise ValueError("Layout has no root node")
    root_bounds.validate()

    leaves: list[LeafRegion] = []

    def walk(node: NodeRecord, bounds: Bounds) -> None:
        children = children_of(nodes, node.node_id)
        if not children:
            leaves.append(
                LeafRegion(
                    node_id=node.node_id,
                    bounds=bounds,
                    color=node.color,
                    label=node.label or f"Region {node.node_id}",
                )
            )
            return

        if len(children) != 2:
            raise ValueError(f"Node {node.node_id} has {len(children)} children; expected 2")
        if node.split_kind == SPLIT_VERTICAL:
            split_x = bounds.x0 + (bounds.x1 - bounds.x0) * node.split_ratio
            child_bounds = [
                Bounds(bounds.x0, bounds.y0, split_x, bounds.y1),
                Bounds(split_x, bounds.y0, bounds.x1, bounds.y1),
            ]
        elif node.split_kind == SPLIT_HORIZONTAL:
            split_y = bounds.y0 + (bounds.y1 - bounds.y0) * node.split_ratio
            child_bounds = [
                Bounds(bounds.x0, bounds.y0, bounds.x1, split_y),
                Bounds(bounds.x0, split_y, bounds.x1, bounds.y1),
            ]
        else:
            raise ValueError(f"Node {node.node_id} has children but no split orientation")

        for child, child_bound in zip(children, child_bounds):
            child_bound.validate()
            walk(child, child_bound)

    walk(root, root_bounds)
    return leaves


def _axis_contains(value: float, lower: float, upper: float) -> bool:
    if lower <= value < upper:
        return True
    return upper == 1.0 and value == 1.0


def find_leaf_at_uv(leaves: Sequence[LeafRegion], u: float, v: float) -> LeafRegion | None:
    if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
        return None

    for leaf in leaves:
        bounds = leaf.bounds
        if _axis_contains(u, bounds.x0, bounds.x1) and _axis_contains(v, bounds.y0, bounds.y1):
            return leaf
    return None


def choose_cut_orientation(bounds: Bounds, u: float, v: float) -> str:
    width = bounds.x1 - bounds.x0
    height = bounds.y1 - bounds.y0
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"Bounds must have positive area: {bounds!r}")

    center_x = (bounds.x0 + bounds.x1) * 0.5
    center_y = (bounds.y0 + bounds.y1) * 0.5
    distance_to_vertical = abs(u - center_x) / width
    distance_to_horizontal = abs(v - center_y) / height
    if distance_to_vertical <= distance_to_horizontal:
        return SPLIT_VERTICAL
    return SPLIT_HORIZONTAL


def clamp_split_ratio(ratio: float) -> float:
    return max(0.001, min(0.999, ratio))


def cursor_split_ratio(bounds: Bounds, orientation: str, u: float, v: float, midpoint_snap: bool = True) -> float:
    bounds.validate()
    if midpoint_snap:
        return 0.5
    if orientation == SPLIT_VERTICAL:
        return clamp_split_ratio((u - bounds.x0) / (bounds.x1 - bounds.x0))
    if orientation == SPLIT_HORIZONTAL:
        return clamp_split_ratio((v - bounds.y0) / (bounds.y1 - bounds.y0))
    raise ValueError(f"Unsupported split orientation: {orientation}")


def cursor_segment_index(bounds: Bounds, orientation: str, u: float, v: float, segment_count: int) -> int:
    bounds.validate()
    if segment_count < 1:
        raise ValueError("Segment count must be at least 1")

    if orientation == SPLIT_VERTICAL:
        ratio = (u - bounds.x0) / (bounds.x1 - bounds.x0)
    elif orientation == SPLIT_HORIZONTAL:
        ratio = (v - bounds.y0) / (bounds.y1 - bounds.y0)
    else:
        raise ValueError(f"Unsupported split orientation: {orientation}")

    return max(0, min(segment_count - 1, int(ratio * segment_count)))


def loop_cut_preview_ratios(cuts: int) -> list[float]:
    if not 1 <= cuts <= 16:
        raise ValueError("Loop cuts must be between 1 and 16")
    segment_count = cuts + 1
    return [index / segment_count for index in range(1, segment_count)]


def grid_preview_ratios(size: int) -> list[float]:
    if not 2 <= size <= 16:
        raise ValueError("Grid size must be between 2 and 16")
    return [index / size for index in range(1, size)]
