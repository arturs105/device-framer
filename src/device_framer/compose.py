"""Compositing a screenshot into a frame PNG."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from PIL import Image, ImageColor, ImageFilter, UnidentifiedImageError

from .console import CliError
from .geometry import Box, enclosed_transparent_mask

Fit = Literal["cover", "contain"]

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic"}


def open_screenshot(path: Path) -> Image.Image:
    if path.suffix.lower() == ".heic":
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            raise CliError("HEIC input needs the optional extra: install with `uv tool install '.[heic]'`") from None
    try:
        return Image.open(path).convert("RGBA")
    except UnidentifiedImageError as exc:
        raise CliError(f"not a readable image: {exc}") from exc


def aspect_mismatch(shot_size: tuple[int, int], screen: Box) -> float:
    """Relative difference between the screenshot aspect and the screen aspect."""
    sw, sh = shot_size
    return abs(sw / sh - screen.aspect) / screen.aspect


class Frame:
    """A loaded frame PNG plus the paste mask derived from its alpha channel."""

    def __init__(self, image: Image.Image) -> None:
        self.image = image.convert("RGBA")
        # Enclosed cutouts only (no exterior transparency), dilated a little so
        # anti-aliased edges are covered by the bezel rather than left as a seam.
        self._cutouts = enclosed_transparent_mask(self.image).filter(ImageFilter.MaxFilter(3))

    @classmethod
    def load(cls, path: Path) -> "Frame":
        with Image.open(path) as img:
            return cls(img)

    def screen_mask(self, screen: Box) -> Image.Image:
        """Inverted alpha inside ``screen``, limited to the enclosed cutout."""
        region = (screen.x, screen.y, screen.x + screen.width, screen.y + screen.height)
        inverted = self.image.crop(region).getchannel("A").point(lambda a: 255 - a)
        return Image.composite(inverted, Image.new("L", screen.size, 0), self._cutouts.crop(region))

    def compose(self, shot: Image.Image, screen: Box, *, fit: Fit = "cover", bg: str | None = None) -> Image.Image:
        fitted = fit_image(shot, screen.size, fit, bg)
        canvas = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        canvas.paste(fitted, (screen.x, screen.y), self.screen_mask(screen))
        canvas.alpha_composite(self.image)
        return canvas


def fit_image(shot: Image.Image, box: tuple[int, int], fit: Fit, bg: str | None) -> Image.Image:
    """Return ``shot`` resized to exactly ``box`` using cover (centre-crop) or contain (letterbox)."""
    bw, bh = box
    sw, sh = shot.size
    scale = max(bw / sw, bh / sh) if fit == "cover" else min(bw / sw, bh / sh)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    resized = shot.resize((nw, nh), Image.Resampling.LANCZOS)
    if fit == "cover":
        left, top = (nw - bw) // 2, (nh - bh) // 2
        return resized.crop((left, top, left + bw, top + bh))
    fill = ImageColor.getcolor(bg, "RGBA") if bg else (0, 0, 0, 0)
    canvas = Image.new("RGBA", (bw, bh), fill)
    canvas.alpha_composite(resized, ((bw - nw) // 2, (bh - nh) // 2))
    return canvas
