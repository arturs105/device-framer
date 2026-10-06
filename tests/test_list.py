from conftest import run_cli


def test_list_shows_devices_colours_orientations_and_screen_sizes(root, phone):
    res = run_cli(root, "list")
    assert res.code == 0
    assert "iphone-17-pro" in res.out and "iPhone 17 Pro" in res.out
    assert "deep-blue" in res.out and "silver" in res.out
    assert "portrait" in res.out and "landscape" in res.out
    assert "260x520" in res.out and "520x260" in res.out


def test_list_with_nothing_installed_points_to_discover(root):
    res = run_cli(root, "list")
    assert res.code == 0
    assert "frames discover" in res.out
