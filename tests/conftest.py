"""Shared fixtures: synthetic frame PNGs and an in-process CLI runner."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

FRAME_RGB = (40, 40, 40)
SHOT_RGB = (200, 30, 90)


def make_frame(
    size: tuple[int, int],
    screen: tuple[int, int, int, int],
    *,
    notch: tuple[int, int, int, int] | None = None,
    round_face: bool = False,
    corner_radius: int = 20,
) -> Image.Image:
    """Opaque rounded rectangle with a transparent screen cutout.

    ``screen`` is (x, y, w, h). ``notch`` is an opaque intrusion drawn
    inside the cutout. ``round_face`` makes the cutout an ellipse.
    """
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=corner_radius, fill=FRAME_RGB + (255,))
    sx, sy, sw, sh = screen
    box = (sx, sy, sx + sw - 1, sy + sh - 1)
    if round_face:
        draw.ellipse(box, fill=(0, 0, 0, 0))
    else:
        draw.rectangle(box, fill=(0, 0, 0, 0))
    if notch:
        nx, ny, nw, nh = notch
        draw.rectangle((nx, ny, nx + nw - 1, ny + nh - 1), fill=FRAME_RGB + (255,))
    return img


def make_shot(size: tuple[int, int], color: tuple[int, int, int] = SHOT_RGB) -> Image.Image:
    return Image.new("RGB", size, color)


@dataclass
class Device:
    slug: str
    name: str
    variants: dict[str, tuple[tuple[int, int], tuple[int, int, int, int]]]
    """color-orientation -> (frame size, screen box)"""


PHONE_PORTRAIT = ((300, 600), (20, 40, 260, 520))
PHONE_LANDSCAPE = ((600, 300), (40, 20, 520, 260))
PHONE_NOTCH = (110, 40, 80, 24)


def install_device(root: Path, device: Device, dmg_url: str = "https://example.invalid/Bezel.dmg") -> None:
    """Write frames + manifest entry under ``root`` as ``frames add`` would."""
    frames_dir = root / "frames"
    manifest_path = root / "devices.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    variants = []
    for key, (size, screen) in device.variants.items():
        color, orientation = key.rsplit("-", 1)
        rel = f"{device.slug}/{color}-{orientation}.png"
        path = frames_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        notch = PHONE_NOTCH if orientation == "portrait" and size == PHONE_PORTRAIT[0] else None
        make_frame(size, screen, notch=notch).save(path)
        variants.append(
            {
                "raw": f"{device.name} - {color.replace('-', ' ').title()} - {orientation.title()}.png",
                "color": color,
                "orientation": orientation,
                "path": rel,
                "screen": {"x": screen[0], "y": screen[1], "width": screen[2], "height": screen[3]},
            }
        )
    manifest[device.slug] = {"name": device.name, "dmg_url": dmg_url, "variants": variants}
    manifest_path.write_text(json.dumps(manifest, indent=2))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "frames").mkdir()
    return tmp_path


@pytest.fixture
def phone(root: Path) -> Device:
    device = Device(
        slug="iphone-17-pro",
        name="iPhone 17 Pro",
        variants={
            "deep-blue-portrait": PHONE_PORTRAIT,
            "deep-blue-landscape": PHONE_LANDSCAPE,
            "silver-portrait": PHONE_PORTRAIT,
        },
    )
    install_device(root, device)
    return device


@dataclass
class Result:
    code: int
    out: str
    err: str


def run_cli(root: Path, *args: str) -> Result:
    """Invoke the CLI in-process with a non-TTY stdin/stdout."""
    from device_framer.cli import main

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(["--frames-dir", str(root / "frames"), *args])
        except SystemExit as exc:  # argparse errors / --help
            code = int(exc.code or 0)
    return Result(code, out.getvalue(), err.getvalue())


def has_hdiutil() -> bool:
    return shutil.which("hdiutil") is not None


def build_dmg(src_dir: Path, dmg_path: Path, volname: str = "Bezels") -> Path:
    subprocess.run(
        ["hdiutil", "create", "-quiet", "-volname", volname, "-srcfolder", str(src_dir), "-ov", "-format", "UDZO", str(dmg_path)],
        check=True,
    )
    return dmg_path


requires_hdiutil = pytest.mark.skipif(not has_hdiutil(), reason="hdiutil not available")
