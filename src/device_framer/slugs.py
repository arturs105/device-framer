"""Slug derivation from Apple's bezel PNG filenames and DMG URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote

SEPARATOR = " - "
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_BEZEL_URL = re.compile(r"""(?:href=["'])?((?:https?|file)://[^"'\s<>]*?/Bezel-[^"'\s<>]+?\.dmg)""", re.IGNORECASE)


def slugify(text: str) -> str:
    return _NON_SLUG.sub("-", text.lower()).strip("-")


@dataclass(frozen=True)
class ParsedName:
    device_name: str
    color_name: str
    orientation_name: str

    @property
    def device_slug(self) -> str:
        return slugify(self.device_name)

    @property
    def color_slug(self) -> str:
        return slugify(self.color_name)

    @property
    def orientation_slug(self) -> str:
        return slugify(self.orientation_name)


def parse_png_name(filename: str) -> ParsedName:
    """``"iPhone 17 Pro - Deep Blue - Portrait.png"`` -> device, colour, orientation.

    Orientation defaults to ``Portrait`` when absent. A single-part name is
    treated as the device with colour ``default``.
    """
    stem = PurePosixPath(filename).stem
    parts = [p.strip() for p in stem.split(SEPARATOR) if p.strip()]
    if not parts:
        raise ValueError(f"cannot parse frame name: {filename!r}")
    device = parts[0]
    color = parts[1] if len(parts) > 1 else "Default"
    orientation = parts[2] if len(parts) > 2 else "Portrait"
    if len(parts) > 3:
        color = SEPARATOR.join(parts[1:-1])
        orientation = parts[-1]
    return ParsedName(device, color, orientation)


def bezel_urls(html: str) -> list[str]:
    seen: list[str] = []
    for m in _BEZEL_URL.finditer(html):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def display_name_from_url(url: str) -> str:
    """``.../Bezel-Apple-Watch-Ultra-3.dmg`` -> ``Apple Watch Ultra 3``."""
    base = url.rsplit("/", 1)[-1]
    base = re.sub(r"\.dmg$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"^Bezel-", "", base)
    return unquote(base).replace("-", " ").replace("_", " ").strip()
