"""devices.json load/save and the path resolution for the frames root."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .geometry import Box

MANIFEST_NAME = "devices.json"
FRAMES_DIRNAME = "frames"


@dataclass
class Variant:
    raw: str
    color: str
    orientation: str
    path: str
    screen: Box | None
    screen_override: Box | None = None

    @property
    def effective_screen(self) -> Box | None:
        return self.screen_override or self.screen

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "raw": self.raw,
            "color": self.color,
            "orientation": self.orientation,
            "path": self.path,
            "screen": _box_to_json(self.screen),
        }
        if self.screen_override:
            d["screen_override"] = _box_to_json(self.screen_override)
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Variant":
        return cls(
            raw=d["raw"],
            color=d["color"],
            orientation=d.get("orientation", "portrait"),
            path=d["path"],
            screen=_box_from_json(d.get("screen")),
            screen_override=_box_from_json(d.get("screen_override")),
        )


@dataclass
class DeviceEntry:
    name: str
    dmg_url: str
    variants: list[Variant] = field(default_factory=list)
    default_color: str | None = None

    def colors(self) -> list[str]:
        seen: list[str] = []
        for v in self.variants:
            if v.color not in seen:
                seen.append(v.color)
        return seen

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "dmg_url": self.dmg_url,
            "variants": [v.to_json() for v in self.variants],
        }
        if self.default_color:
            d["default_color"] = self.default_color
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "DeviceEntry":
        return cls(
            name=d["name"],
            dmg_url=d["dmg_url"],
            variants=[Variant.from_json(v) for v in d.get("variants", [])],
            default_color=d.get("default_color"),
        )


def _box_to_json(box: Box | None) -> dict[str, int] | None:
    if box is None:
        return None
    return {"x": box.x, "y": box.y, "width": box.width, "height": box.height}


def _box_from_json(d: dict[str, int] | None) -> Box | None:
    if not d:
        return None
    return Box(int(d["x"]), int(d["y"]), int(d["width"]), int(d["height"]))


@dataclass
class Store:
    """The frames directory and the manifest that describes it."""

    frames_dir: Path
    manifest_path: Path
    devices: dict[str, DeviceEntry] = field(default_factory=dict)

    @classmethod
    def open(cls, frames_dir: Path) -> "Store":
        frames_dir = frames_dir.expanduser().resolve()
        manifest_path = frames_dir.parent / MANIFEST_NAME
        store = cls(frames_dir, manifest_path)
        if manifest_path.exists():
            raw = json.loads(manifest_path.read_text())
            store.devices = {slug: DeviceEntry.from_json(e) for slug, e in raw.items()}
        return store

    def save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = {slug: self.devices[slug].to_json() for slug in sorted(self.devices)}
        self.manifest_path.write_text(json.dumps(data, indent=2) + "\n")

    def frame_path(self, variant: Variant) -> Path:
        return self.frames_dir / variant.path


def default_frames_dir() -> Path:
    """Resolve the frames root.

    ``$DEVICE_FRAMER_HOME/frames`` when set; otherwise the ``frames/`` folder
    of the source checkout this package runs from. When the package is
    installed into a tool environment (no checkout), ``~/.device-framer/frames``.
    """
    env = os.environ.get("DEVICE_FRAMER_HOME")
    if env:
        return Path(env).expanduser() / FRAMES_DIRNAME
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "device_framer").exists():
            return parent / FRAMES_DIRNAME
    return Path.home() / ".device-framer" / FRAMES_DIRNAME
