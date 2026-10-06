from PIL import Image

from conftest import make_frame
from device_framer.geometry import Box, detect_screen


def test_rectangular_cutout_bounding_box():
    frame = make_frame((100, 200), (10, 20, 80, 160))
    assert detect_screen(frame) == Box(10, 20, 80, 160)


def test_notch_intrusion_does_not_shrink_box():
    frame = make_frame((100, 200), (10, 20, 80, 160), notch=(40, 20, 20, 10))
    assert detect_screen(frame) == Box(10, 20, 80, 160)


def test_round_face_box_is_the_circle_bounds():
    frame = make_frame((120, 120), (10, 10, 100, 100), round_face=True)
    assert detect_screen(frame) == Box(10, 10, 100, 100)


def test_exterior_transparency_is_ignored():
    # Large transparent margin around the device must not win over the cutout.
    frame = make_frame((100, 200), (10, 20, 80, 160), corner_radius=40)
    padded = Image.new("RGBA", (400, 500), (0, 0, 0, 0))
    padded.paste(frame, (150, 150))
    assert detect_screen(padded) == Box(160, 170, 80, 160)


def test_small_holes_lose_to_the_screen():
    frame = make_frame((100, 200), (10, 20, 80, 160))
    # a tiny transparent speaker hole in the bezel
    frame.paste((0, 0, 0, 0), (45, 5, 55, 8))
    assert detect_screen(frame) == Box(10, 20, 80, 160)


def test_no_enclosed_region_returns_none():
    assert detect_screen(Image.new("RGBA", (50, 50), (0, 0, 0, 255))) is None
