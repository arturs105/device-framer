"""frames discover / add / sync / remove against synthetic DMGs and a stubbed Apple page."""

import json
from pathlib import Path

import pytest
from PIL import Image

from conftest import SHOT_RGB, build_dmg, make_frame, make_shot, requires_hdiutil, run_cli

APPLE_PAGE = """
<html><body>
<a href="https://devimages-cdn.apple.com/design/resources/download/Bezel-iPhone-17.dmg">iPhone 17</a>
<a href="https://devimages-cdn.apple.com/design/resources/download/Bezel-Apple-Watch-Ultra-3.dmg">Watch</a>
<a href="https://devimages-cdn.apple.com/design/resources/download/Bezel-iPad-Pro-M5.dmg">iPad</a>
<a href="https://devimages-cdn.apple.com/design/resources/download/Fonts-SF.dmg">not a bezel</a>
</body></html>
"""


@pytest.fixture
def apple_page(tmp_path, monkeypatch):
    page = tmp_path / "resources.html"
    page.write_text(APPLE_PAGE)
    monkeypatch.setenv("DEVICE_FRAMER_RESOURCES_URL", page.as_uri())
    return page


def test_discover_lists_bezels_not_in_manifest(root, apple_page):
    res = run_cli(root, "frames", "discover")
    assert res.code == 0
    assert "iPhone 17" in res.out and "Apple Watch Ultra 3" in res.out and "iPad Pro M5" in res.out
    assert "Fonts" not in res.out


def test_discover_hides_devices_already_in_manifest(root, apple_page):
    (root / "devices.json").write_text(json.dumps({
        "iphone-17-pro": {"name": "iPhone 17 Pro", "variants": [],
                           "dmg_url": "https://devimages-cdn.apple.com/design/resources/download/Bezel-iPhone-17.dmg"}
    }))
    res = run_cli(root, "frames", "discover")
    assert res.code == 0
    assert "iPhone 17" not in res.out
    assert "Apple Watch Ultra 3" in res.out


def test_discover_reports_zero_results_gracefully(root, tmp_path, monkeypatch):
    page = tmp_path / "empty.html"
    page.write_text("<html>redesigned</html>")
    monkeypatch.setenv("DEVICE_FRAMER_RESOURCES_URL", page.as_uri())
    res = run_cli(root, "frames", "discover")
    assert res.code == 0
    assert page.as_uri() in res.out
    assert "frames add" in res.out  # hint to pass a raw URL


# --------------------------------------------------------------------------- #
# add / sync / remove need a real DMG
# --------------------------------------------------------------------------- #

RAW_NAMES = {
    "iPhone 17 Pro - Deep Blue - Portrait.png": ((300, 600), (20, 40, 260, 520)),
    "iPhone 17 Pro - Deep Blue - Landscape.png": ((600, 300), (40, 20, 520, 260)),
    "iPhone 17 Pro - Silver - Portrait.png": ((300, 600), (20, 40, 260, 520)),
    "iPhone 17 - Black - Portrait.png": ((280, 580), (20, 40, 240, 500)),
}


@pytest.fixture(scope="module")
def dmg(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("dmg")
    src = base / "dmg-src" / "iPhone 17" / "PNG"
    src.mkdir(parents=True)
    for name, (size, screen) in RAW_NAMES.items():
        make_frame(size, screen).save(src / name)
    (src / "iPhone 17 Pro.psd").write_bytes(b"photoshop")
    return build_dmg(base / "dmg-src", base / "Bezel-iPhone-17.dmg")


@requires_hdiutil
def test_add_with_variants_copies_only_those_and_records_geometry(root, dmg):
    res = run_cli(
        root, "frames", "add", str(dmg),
        "--variants", "iPhone 17 Pro - Deep Blue - Portrait.png,iPhone 17 Pro - Deep Blue - Landscape.png",
    )
    assert res.code == 0, res.err
    frames = root / "frames" / "iphone-17-pro"
    assert sorted(p.name for p in frames.iterdir()) == ["deep-blue-landscape.png", "deep-blue-portrait.png"]
    assert not (root / "frames" / "iphone-17").exists()
    manifest = json.loads((root / "devices.json").read_text())
    entry = manifest["iphone-17-pro"]
    assert entry["name"] == "iPhone 17 Pro"
    assert entry["dmg_url"] == str(dmg)
    raws = {v["raw"]: v for v in entry["variants"]}
    assert set(raws) == {"iPhone 17 Pro - Deep Blue - Portrait.png", "iPhone 17 Pro - Deep Blue - Landscape.png"}
    assert raws["iPhone 17 Pro - Deep Blue - Portrait.png"]["screen"] == {"x": 20, "y": 40, "width": 260, "height": 520}
    assert raws["iPhone 17 Pro - Deep Blue - Portrait.png"]["color"] == "deep-blue"
    assert raws["iPhone 17 Pro - Deep Blue - Landscape.png"]["orientation"] == "landscape"
    # detected sizes are printed for verification
    assert "260x520" in res.out and "520x260" in res.out
    # the downloaded copy is gone, the original local DMG is untouched
    assert dmg.exists()
    assert not list((root).rglob("*.dmg"))


@requires_hdiutil
def test_add_all_installs_every_png_grouped_by_device(root, dmg):
    res = run_cli(root, "frames", "add", str(dmg), "--all")
    assert res.code == 0, res.err
    manifest = json.loads((root / "devices.json").read_text())
    assert set(manifest) == {"iphone-17-pro", "iphone-17"}
    assert len(manifest["iphone-17-pro"]["variants"]) == 3
    assert (root / "frames" / "iphone-17" / "black-portrait.png").exists()


@requires_hdiutil
def test_add_then_frame_round_trip(root, dmg, tmp_path):
    run_cli(root, "frames", "add", str(dmg), "--variants", "iPhone 17 Pro - Silver - Portrait.png")
    make_shot((260, 520)).save(tmp_path / "shot.png")
    res = run_cli(root, str(tmp_path / "shot.png"), "--device", "iphone-17-pro", "--color", "silver")
    assert res.code == 0, res.err
    assert Image.open(tmp_path / "shot-framed.png").getpixel((150, 300))[:3] == SHOT_RGB


@requires_hdiutil
def test_readd_replaces_variant_list(root, dmg):
    run_cli(root, "frames", "add", str(dmg), "--variants", "iPhone 17 Pro - Deep Blue - Portrait.png")
    res = run_cli(root, "frames", "add", str(dmg), "--variants", "iPhone 17 Pro - Silver - Portrait.png")
    assert res.code == 0, res.err
    manifest = json.loads((root / "devices.json").read_text())
    assert [v["raw"] for v in manifest["iphone-17-pro"]["variants"]] == ["iPhone 17 Pro - Silver - Portrait.png"]
    assert sorted(p.name for p in (root / "frames" / "iphone-17-pro").iterdir()) == ["silver-portrait.png"]


@requires_hdiutil
def test_add_unknown_variant_name_fails_and_lists_available(root, dmg):
    res = run_cli(root, "frames", "add", str(dmg), "--variants", "iPhone 99 - Gold - Portrait.png")
    assert res.code == 1
    assert "iPhone 17 Pro - Deep Blue - Portrait.png" in res.err
    assert not (root / "devices.json").exists()


@requires_hdiutil
def test_add_without_variants_under_non_tty_fails_and_lists_available(root, dmg):
    res = run_cli(root, "frames", "add", str(dmg))
    assert res.code == 1
    assert "--variants" in res.err and "--all" in res.err
    assert "iPhone 17 - Black - Portrait.png" in res.err


@requires_hdiutil
def test_add_by_discover_name(root, dmg, tmp_path, monkeypatch):
    page = tmp_path / "page.html"
    page.write_text(f'<a href="{dmg.as_uri()}">x</a>')
    monkeypatch.setenv("DEVICE_FRAMER_RESOURCES_URL", page.as_uri())
    res = run_cli(root, "frames", "add", "iphone 17", "--variants", "iPhone 17 - Black - Portrait.png")
    assert res.code == 0, res.err
    assert (root / "frames" / "iphone-17" / "black-portrait.png").exists()


@requires_hdiutil
def test_sync_restores_missing_frames_without_prompting(root, dmg):
    run_cli(root, "frames", "add", str(dmg), "--all")
    (root / "frames" / "iphone-17-pro" / "silver-portrait.png").unlink()
    (root / "frames" / "iphone-17" / "black-portrait.png").unlink()
    before = (root / "devices.json").read_text()
    res = run_cli(root, "frames", "sync")
    assert res.code == 0, res.err
    assert (root / "frames" / "iphone-17-pro" / "silver-portrait.png").exists()
    assert (root / "frames" / "iphone-17" / "black-portrait.png").exists()
    assert (root / "devices.json").read_text() == before
    assert "silver-portrait.png" in res.out


def test_sync_with_nothing_missing_is_a_noop(root, phone):
    res = run_cli(root, "frames", "sync")
    assert res.code == 0
    assert "up to date" in res.out


def test_remove_deletes_frames_and_manifest_entry(root, phone):
    res = run_cli(root, "frames", "remove", "iphone-17-pro", "--yes")
    assert res.code == 0, res.err
    assert not (root / "frames" / "iphone-17-pro").exists()
    assert json.loads((root / "devices.json").read_text()) == {}


def test_remove_without_yes_under_non_tty_refuses(root, phone):
    res = run_cli(root, "frames", "remove", "iphone-17-pro")
    assert res.code == 1
    assert "--yes" in res.err
    assert (root / "frames" / "iphone-17-pro").exists()


def test_remove_unknown_device_errors(root, phone):
    res = run_cli(root, "frames", "remove", "nokia", "--yes")
    assert res.code == 1
    assert "iphone-17-pro" in res.err


def test_add_with_unknown_name_fails_without_guessing(root, apple_page):
    res = run_cli(root, "frames", "add", "Nokia 3310", "--all")
    assert res.code == 1
    assert "frames discover" in res.err and "Bezel-" in res.err
