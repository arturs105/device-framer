import pytest

from conftest import run_cli


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_top_level_help_explains_workflow_with_examples(root, flag):
    res = run_cli(root, flag)
    assert res.code == 0
    out = res.out
    assert "examples:" in out
    assert "--device" in out and "--color" in out
    assert "device-framer list" in out
    for sub in ("frames discover", "frames add", "frames sync", "frames remove"):
        assert sub in out


@pytest.mark.parametrize(
    "args, expect",
    [
        (["list", "--help"], "List installed devices"),
        (["frames", "--help"], "discover"),
        (["frames", "discover", "--help"], "design resources"),
        (["frames", "add", "--help"], "--variants"),
        (["frames", "sync", "--help"], "missing"),
        (["frames", "remove", "--help"], "--yes"),
    ],
)
def test_each_subcommand_has_its_own_help(root, args, expect):
    res = run_cli(root, *args)
    assert res.code == 0
    assert expect in res.out


def test_no_arguments_shows_usage_error(root):
    res = run_cli(root)
    assert res.code == 2
    assert "usage" in res.err
