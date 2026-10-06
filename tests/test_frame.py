import json
from pathlib import Path

from PIL import Image

from conftest import FRAME_RGB, PHONE_NOTCH, PHONE_PORTRAIT, SHOT_RGB, Device, install_device, make_shot, run_cli


def shot(path: Path, size=(260, 520), color=SHOT_RGB) -> Path:
    make_shot(size, color).save(path)
    return path


def test_single_file_framed_next_to_input(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0, res.err
    out = Image.open(tmp_path / "shot-framed.png")
    assert out.size == PHONE_PORTRAIT[0]
    assert out.mode == "RGBA"
    # screen centre comes from the screenshot
    assert out.getpixel((150, 300))[:3] == SHOT_RGB
    # notch region comes from the frame
    nx, ny, nw, nh = PHONE_NOTCH
    assert out.getpixel((nx + nw // 2, ny + nh // 2))[:3] == FRAME_RGB
    # outside the device stays transparent (rounded corner)
    assert out.getpixel((0, 0))[3] == 0


def test_folder_input_frames_every_supported_image(root, phone, tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    shot(folder / "a.png")
    shot(folder / "b.jpg")
    make_shot((260, 520)).save(folder / "c.webp")
    (folder / "notes.txt").write_text("skip me")
    sub = folder / "nested"
    sub.mkdir()
    shot(sub / "deep.png")
    res = run_cli(root, str(folder), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0, res.err
    assert sorted(p.name for p in folder.glob("*-framed.png")) == ["a-framed.png", "b-framed.png", "c-framed.png"]
    assert not (sub / "deep-framed.png").exists()


def test_recursive_flag_descends_into_subfolders(root, phone, tmp_path):
    folder = tmp_path / "shots"
    sub = folder / "nested"
    sub.mkdir(parents=True)
    shot(folder / "a.png")
    shot(sub / "deep.png")
    res = run_cli(root, str(folder), "-r", "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0, res.err
    assert (sub / "deep-framed.png").exists()


def test_output_dir_for_batch_mirrors_structure(root, phone, tmp_path):
    folder = tmp_path / "shots"
    (folder / "nested").mkdir(parents=True)
    shot(folder / "a.png")
    shot(folder / "nested" / "b.png")
    out = tmp_path / "out"
    res = run_cli(root, str(folder), "-r", "-o", str(out), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0, res.err
    assert (out / "a-framed.png").exists()
    assert (out / "nested" / "b-framed.png").exists()
    assert not (folder / "a-framed.png").exists()


def test_output_file_for_single_input(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    dest = tmp_path / "custom" / "hero.png"
    res = run_cli(root, str(src), "-o", str(dest), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0, res.err
    assert dest.exists()


def test_existing_output_is_overwritten(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    dest = tmp_path / "shot-framed.png"
    dest.write_bytes(b"stale")
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0
    assert Image.open(dest).size == PHONE_PORTRAIT[0]


def test_cover_centre_crops_oversized_input(root, phone, tmp_path):
    # Wide left/right stripes should be cropped away: a 2:1-wider image whose
    # centre third is SHOT_RGB and edges are green.
    img = Image.new("RGB", (780, 520), (0, 255, 0))
    img.paste(Image.new("RGB", (260, 520), SHOT_RGB), (260, 0))
    img.save(tmp_path / "wide.png")
    res = run_cli(root, str(tmp_path / "wide.png"), "--device", "iphone-17-pro", "--color", "deep-blue", "--orientation", "portrait")
    assert res.code == 0, res.err
    out = Image.open(tmp_path / "wide-framed.png")
    # left edge of screen (x=20) still shows the centre colour, not green
    assert out.getpixel((22, 300))[:3] == SHOT_RGB
    assert "warning" in res.err and "aspect" in res.err


def test_contain_letterboxes_with_background(root, phone, tmp_path):
    img = Image.new("RGB", (260, 260), SHOT_RGB)  # square into a 1:2 screen
    img.save(tmp_path / "sq.png")
    res = run_cli(
        root, str(tmp_path / "sq.png"), "--device", "iphone-17-pro", "--color", "deep-blue",
        "--orientation", "portrait", "--fit", "contain", "--bg", "#00ff00",
    )
    assert res.code == 0, res.err
    out = Image.open(tmp_path / "sq-framed.png")
    assert out.getpixel((150, 300))[:3] == SHOT_RGB
    assert out.getpixel((150, 80))[:3] == (0, 255, 0)  # letterbox band inside the screen


def test_no_aspect_warning_when_input_matches(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert "warning" not in res.err


def test_orientation_auto_picked_from_aspect(root, phone, tmp_path):
    src = shot(tmp_path / "land.png", size=(520, 260))
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 0, res.err
    assert Image.open(tmp_path / "land-framed.png").size == (600, 300)


def test_orientation_override_wins(root, phone, tmp_path):
    src = shot(tmp_path / "land.png", size=(520, 260))
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue", "--orientation", "portrait")
    assert res.code == 0, res.err
    assert Image.open(tmp_path / "land-framed.png").size == (300, 600)


def test_unknown_orientation_lists_valid_ones(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue", "--orientation", "upside-down")
    assert res.code == 1
    assert "portrait" in res.err and "landscape" in res.err


def test_square_input_with_no_matching_variant_errors_under_non_tty(root, phone, tmp_path):
    src = shot(tmp_path / "sq.png", size=(300, 300))
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 1
    assert "--orientation" in res.err and "portrait" in res.err and "landscape" in res.err


def test_missing_device_flag_fails_fast_with_valid_values(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src))
    assert res.code == 1
    assert "iphone-17-pro" in res.err
    assert not (tmp_path / "shot-framed.png").exists()


def test_missing_color_flag_fails_fast_with_valid_values(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "iphone-17-pro")
    assert res.code == 1
    assert "deep-blue" in res.err and "silver" in res.err


def test_single_installed_colour_is_used_without_prompt(root, tmp_path):
    install_device(root, Device("ipad", "iPad", {"gray-portrait": PHONE_PORTRAIT}))
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "ipad")
    assert res.code == 0, res.err


def test_invalid_colour_names_valid_colours(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "hot-pink")
    assert res.code == 1
    assert "hot-pink" in res.err and "deep-blue" in res.err and "silver" in res.err


def test_unknown_device_names_valid_devices(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "--device", "nokia", "--color", "x")
    assert res.code == 1
    assert "iphone-17-pro" in res.err


def test_batch_continues_after_a_bad_file_and_exits_non_zero(root, phone, tmp_path):
    folder = tmp_path / "shots"
    folder.mkdir()
    shot(folder / "a.png")
    (folder / "broken.png").write_bytes(b"not a png")
    res = run_cli(root, str(folder), "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 1
    assert (folder / "a-framed.png").exists()
    assert "broken.png" in res.err


def test_screen_override_takes_precedence(root, phone, tmp_path):
    manifest = root / "devices.json"
    data = json.loads(manifest.read_text())
    v = next(v for v in data["iphone-17-pro"]["variants"] if v["orientation"] == "portrait" and v["color"] == "silver")
    v["screen_override"] = {"x": 20, "y": 40, "width": 260, "height": 260}
    manifest.write_text(json.dumps(data))
    src = shot(tmp_path / "sq.png", size=(260, 260))
    res = run_cli(root, str(src), "--device", "iphone-17-pro", "--color", "silver")
    assert res.code == 0, res.err
    assert "warning" not in res.err


def test_stray_positional_argument_is_rejected(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src), "oops", "--device", "iphone-17-pro", "--color", "deep-blue")
    assert res.code == 2
    assert not (tmp_path / "shot-framed.png").exists()


def test_missing_device_flag_also_lists_colours(root, phone, tmp_path):
    src = shot(tmp_path / "shot.png")
    res = run_cli(root, str(src))
    assert "deep-blue" in res.err and "silver" in res.err


def test_round_face_masks_screenshot_to_the_circle(root, tmp_path):
    from conftest import make_frame

    # A watch: 200x200 frame, circular cutout filling (20,20)-(180,180), and a
    # transparent exterior so leaks outside the silhouette would be visible.
    frame = make_frame((200, 200), (20, 20, 160, 160), round_face=True, corner_radius=90)
    (root / "frames" / "watch").mkdir(parents=True)
    frame.save(root / "frames" / "watch" / "black-portrait.png")
    (root / "devices.json").write_text(json.dumps({
        "watch": {"name": "Watch", "dmg_url": "x", "variants": [{
            "raw": "Watch - Black.png", "color": "black", "orientation": "portrait",
            "path": "watch/black-portrait.png", "screen": {"x": 20, "y": 20, "width": 160, "height": 160}}]}
    }))
    shot(tmp_path / "face.png", size=(160, 160))
    res = run_cli(root, str(tmp_path / "face.png"), "--device", "watch")
    assert res.code == 0, res.err
    out = Image.open(tmp_path / "face-framed.png")
    assert out.getpixel((100, 100))[:3] == SHOT_RGB  # centre of the face
    assert out.getpixel((40, 40))[:3] == FRAME_RGB  # inside the bezel, outside the circle
    assert out.getpixel((22, 22))[3] == 0  # screen-box corner lies outside the silhouette: no leak
