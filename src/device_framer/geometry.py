"""Screen-cutout detection from a frame PNG's alpha channel.

The screen is the largest transparent connected region that is fully
enclosed by opaque pixels (i.e. does not touch the image border). Regions
are found with a run-length union-find so even multi-megapixel frames are
processed in well under a second without numpy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

# Pixels at or below this alpha count as transparent. Exported PNGs often
# carry stray alpha values of 1-2 inside an otherwise clear cutout, so a
# small tolerance keeps the region in one piece; anti-aliased edges (alpha
# well above this) stay with the bezel and are handled by the paste mask.
TRANSPARENT_MAX_ALPHA = 15
_RUN = re.compile(rb"\x01+")


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    width: int
    height: int

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def __str__(self) -> str:
        return f"{self.width}x{self.height} at {self.x},{self.y}"


@dataclass
class _Component:
    area: int = 0
    x0: int = 1 << 30
    y0: int = 1 << 30
    x1: int = -1
    y1: int = -1
    touches_border: bool = False
    runs: list[tuple[int, int, int]] = field(default_factory=list)  # (y, start, end)

    def absorb(self, other: "_Component") -> None:
        self.area += other.area
        self.x0, self.y0 = min(self.x0, other.x0), min(self.y0, other.y0)
        self.x1, self.y1 = max(self.x1, other.x1), max(self.y1, other.y1)
        self.touches_border = self.touches_border or other.touches_border
        self.runs.extend(other.runs)

    @property
    def box(self) -> Box:
        return Box(self.x0, self.y0, self.x1 - self.x0 + 1, self.y1 - self.y0 + 1)


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _alpha(image: Image.Image) -> Image.Image:
    return image.getchannel("A") if image.mode == "RGBA" else image.convert("RGBA").getchannel("A")


def _enclosed_components(image: Image.Image) -> list[_Component]:
    """Connected transparent regions that do not touch the image border."""
    width, height = image.size
    data = _alpha(image).point(lambda a: 1 if a <= TRANSPARENT_MAX_ALPHA else 0).tobytes()

    parent: list[int] = []
    comps: list[_Component] = []
    prev_runs: list[tuple[int, int, int]] = []  # (start, end, comp index)

    for y in range(height):
        row = data[y * width : (y + 1) * width]
        runs: list[tuple[int, int, int]] = []
        for m in _RUN.finditer(row):
            s, e = m.start(), m.end()
            idx = -1
            for ps, pe, pidx in prev_runs:
                if ps < e and s < pe:  # 4-connected overlap
                    root = _find(parent, pidx)
                    if idx == -1:
                        idx = root
                    elif root != idx:
                        parent[root] = idx
            if idx == -1:
                idx = len(parent)
                parent.append(idx)
                comps.append(_Component())
            c = comps[idx]
            c.area += e - s
            c.x0, c.x1 = min(c.x0, s), max(c.x1, e - 1)
            c.y0, c.y1 = min(c.y0, y), max(c.y1, y)
            c.runs.append((y, s, e))
            if y == 0 or y == height - 1 or s == 0 or e == width:
                c.touches_border = True
            runs.append((s, e, idx))
        prev_runs = runs

    merged: dict[int, _Component] = {}
    for i, c in enumerate(comps):
        root = _find(parent, i)
        if root in merged:
            merged[root].absorb(c)
        else:
            merged[root] = c
    return [c for c in merged.values() if not c.touches_border]


def detect_screen(image: Image.Image) -> Box | None:
    """Return the bounding box of the screen cutout, or ``None`` when no enclosed region exists."""
    enclosed = _enclosed_components(image)
    if not enclosed:
        return None
    return max(enclosed, key=lambda c: c.area).box


def enclosed_transparent_mask(image: Image.Image) -> Image.Image:
    """``L`` mask that is 255 on every enclosed transparent pixel and 0 elsewhere.

    Exterior transparency (outside the device silhouette) is excluded, so a
    screenshot pasted through this mask can never leak past the bezel.
    """
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    for comp in _enclosed_components(image):
        for y, s, e in comp.runs:
            draw.line((s, y, e - 1, y), fill=255)
    return mask
