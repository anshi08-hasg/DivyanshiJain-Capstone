"""Reusable, provider-agnostic layout primitives shared by figma_layout.py
(Themes/Insights/Contradictions/Research Gaps/Design Opportunities) and
persona_layout.py (User Personas). Pure geometry - no MCP calls, no
FigJam-specific concepts - so it can be unit-tested without a live board and
reused anywhere a "place N boxes without overlapping" problem comes up.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


def rects_overlap(a: Rect, b: Rect, margin: float = 0) -> bool:
    """True if a and b intersect, including a safety margin around each -
    two rects exactly touching edge-to-edge (no margin) do not count as
    overlapping, but anything closer than `margin` does."""
    return not (
        a.right + margin <= b.x
        or b.right + margin <= a.x
        or a.bottom + margin <= b.y
        or b.bottom + margin <= a.y
    )


def bounding_box(rects: list[Rect]) -> Rect | None:
    """Smallest rect containing all given rects, or None if the list is empty."""
    if not rects:
        return None
    min_x = min(r.x for r in rects)
    min_y = min(r.y for r in rects)
    max_x = max(r.right for r in rects)
    max_y = max(r.bottom for r in rects)
    return Rect(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)


def find_overlap(rects: list[Rect], margin: float = 0) -> tuple[int, int] | None:
    """Returns the (i, j) index pair of the first overlapping pair found, or
    None if the whole layout is collision-free. Used as a pre-push safety
    check: a real layout bug should fail loudly in code, not silently ship a
    visually broken board."""
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rects_overlap(rects[i], rects[j], margin):
                return i, j
    return None


def assert_no_overlaps(rects: list[Rect], margin: float = 0, label: str = "layout") -> None:
    collision = find_overlap(rects, margin)
    if collision is not None:
        i, j = collision
        raise ValueError(
            f"{label}: element {i} {rects[i]} overlaps element {j} {rects[j]} "
            f"(required margin: {margin}px) - refusing to push a broken layout."
        )


def grid_positions(
    count: int,
    columns: int,
    cell_width: float,
    cell_height: float,
    h_gap: float,
    v_gap: float,
    origin_x: float = 0,
    origin_y: float = 0,
) -> list[Rect]:
    """Deterministic row-major grid: column = i % columns, row = i // columns.
    Every cell has identical width/height - callers with variable-height
    content (e.g. a row of cards with different amounts of text) should
    instead size each row by its own tallest cell; this helper is for the
    common case of uniform cells (sticky notes)."""
    positions = []
    for i in range(count):
        col = i % columns
        row = i // columns
        positions.append(Rect(
            x=origin_x + col * (cell_width + h_gap),
            y=origin_y + row * (cell_height + v_gap),
            width=cell_width,
            height=cell_height,
        ))
    return positions
