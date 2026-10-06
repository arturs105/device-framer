"""Command line entry point for device-framer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import compose as comp
from .console import PROG, CliError, is_interactive, warn
from .manifest import DeviceEntry, Store, Variant, default_frames_dir

EPILOG = """\
examples:
  device-framer shot.png --device iphone-17-pro --color deep-blue
  device-framer shots/ -r -o framed/ --device ipad-pro-m5 --color space-black
  device-framer shot.png --fit contain --bg '#000'
  device-framer list
  device-framer frames discover
  device-framer frames add "iPhone 17" --variants "iPhone 17 Pro - Deep Blue - Portrait.png"
  device-framer frames add https://devimages-cdn.apple.com/design/resources/download/Bezel-iPhone-17.dmg --all
  device-framer frames sync
  device-framer frames remove iphone-17-pro --yes

workflow:
  1. `frames discover` lists Apple bezel DMGs you have not added yet and, on a
     terminal, lets you tick the ones to install right away.
  2. `frames add <name|url>` downloads one, lets you pick the PNG variants to
     keep, copies them into frames/<device>/<color>-<orientation>.png and
     records the choice (plus detected screen geometry) in devices.json.
  3. Frame screenshots with `device-framer <file|folder> --device X --color Y`.
     Omit the flags for an arrow-key picker. Output goes next to the input as
     <name>-framed.png unless -o is given.
  4. On a fresh clone, `frames sync` restores every frame listed in the manifest.
"""

SUBCOMMANDS = ("list", "frames")


def frames_dir_parent() -> argparse.ArgumentParser:
    """Parent parser carrying the global ``--frames-dir`` flag, so every (sub)command accepts it."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--frames-dir", type=Path, default=None, help="frames root (default: ./frames or $DEVICE_FRAMER_HOME/frames)")
    return p


def build_frame_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="Composite screenshots into Apple device bezels. Subcommands: list, frames.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[frames_dir_parent()],
    )
    p.add_argument("input", type=Path, help="screenshot file or folder of screenshots")
    p.add_argument("--device", help="device slug (see `list`); prompts when omitted")
    p.add_argument("--color", help="colour slug for the device; prompts when omitted")
    p.add_argument("--orientation", help="force a variant orientation instead of auto-picking from the input aspect")
    p.add_argument("--fit", choices=["cover", "contain"], default="cover", help="cover: fill and centre-crop (default); contain: letterbox")
    p.add_argument("--bg", help="background colour for --fit contain, e.g. '#000' or 'white'")
    p.add_argument("-o", "--output", type=Path, help="output file (single input) or directory (folder input)")
    p.add_argument("-r", "--recursive", action="store_true", help="recurse into subfolders")
    return p


def build_list_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog=f"{PROG} list",
        description="List installed devices, colours, orientations and screen sizes.",
        parents=[frames_dir_parent()],
    )


# --------------------------------------------------------------------------- #
# Device / colour / variant resolution
# --------------------------------------------------------------------------- #


def pick_one(message: str, choices: list[str], default: str | None = None) -> str | None:
    """Arrow-key single select; returns None when not interactive or cancelled."""
    if not is_interactive():
        return None
    try:
        import questionary

        return questionary.select(message, choices=choices, default=default).ask()  # type: ignore[no-any-return]
    except Exception:
        return None


def describe_devices(store: Store) -> str:
    return "\n".join(f"  {slug}: {', '.join(store.devices[slug].colors()) or '(no colours)'}" for slug in sorted(store.devices))


def resolve_device(store: Store, slug: str | None) -> tuple[str, DeviceEntry]:
    if not store.devices:
        raise CliError("no frames installed; run `device-framer frames discover` and `frames add <name>` first")
    if slug is None:
        slug = pick_one("Device:", sorted(store.devices))
        if slug is None:
            raise CliError("--device is required (no terminal for the picker). Valid devices and colours:\n" + describe_devices(store))
    if slug not in store.devices:
        raise CliError(f"unknown device '{slug}'. Valid devices and colours:\n" + describe_devices(store))
    return slug, store.devices[slug]


def resolve_color(device_slug: str, device: DeviceEntry, color: str | None) -> str:
    valid = device.colors()
    if color is None:
        if len(valid) == 1:
            return valid[0]
        color = pick_one("Colour:", valid, default=device.default_color)
        if color is None:
            raise CliError(f"--color is required (no terminal for the picker). Valid colours for {device_slug}: " + ", ".join(valid))
    if color not in valid:
        raise CliError(f"colour '{color}' is not installed for {device_slug}. Valid colours: " + ", ".join(valid))
    return color


def orientation_class(w: int, h: int) -> str:
    if w == h:
        return "square"
    return "landscape" if w > h else "portrait"


def resolve_variant(
    device_slug: str, device: DeviceEntry, color: str, orientation: str | None, shot_size: tuple[int, int]
) -> Variant:
    candidates = [v for v in device.variants if v.color == color and v.effective_screen]
    if not candidates:
        raise CliError(f"no usable variants for {device_slug} {color}; try `frames sync`")
    orientations = sorted({v.orientation for v in candidates})
    if orientation is not None:
        for v in candidates:
            if v.orientation == orientation:
                return v
        raise CliError(f"orientation '{orientation}' is not installed for {device_slug} {color}. Valid orientations: " + ", ".join(orientations))
    if len(candidates) == 1:
        return candidates[0]

    sw, sh = shot_size
    shot_aspect = sw / sh
    ranked = sorted(
        ((abs(shot_aspect - v.effective_screen.aspect), v) for v in candidates if v.effective_screen and orientation_class(*v.effective_screen.size) == orientation_class(sw, sh)),
        key=lambda t: t[0],
    )
    if ranked and (len(ranked) == 1 or ranked[0][0] < ranked[1][0]):
        return ranked[0][1]

    chosen = pick_one(f"Orientation for {sw}x{sh} input:", orientations)
    for v in candidates:
        if v.orientation == chosen:
            return v
    raise CliError(f"cannot pick an orientation for a {sw}x{sh} input; pass --orientation. Valid orientations: " + ", ".join(orientations))


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #

FRAMED_SUFFIX = "-framed"


def collect_inputs(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise CliError(f"input not found: {path}")
    it = path.rglob("*") if recursive else path.iterdir()
    # Earlier outputs live beside their inputs, so skip them on re-runs.
    files = [p for p in it if p.is_file() and p.suffix.lower() in comp.SUPPORTED_EXTENSIONS and not p.stem.endswith(FRAMED_SUFFIX)]
    return sorted(files)


def output_path(src: Path, input_root: Path, out: Path | None, batch: bool) -> Path:
    name = src.stem + FRAMED_SUFFIX + ".png"
    if out is None:
        return src.with_name(name)
    if not batch:
        return out / name if out.is_dir() else out
    rel = src.relative_to(input_root) if src.is_relative_to(input_root) else Path(src.name)
    return out / rel.with_name(name)


def cmd_frame(args: argparse.Namespace, store: Store) -> int:
    inputs = collect_inputs(args.input, args.recursive)
    batch = args.input.is_dir()
    if not inputs:
        raise CliError(f"no supported images ({', '.join(sorted(comp.SUPPORTED_EXTENSIONS))}) found in {args.input}")
    if args.bg and args.fit != "contain":
        warn("--bg only applies with --fit contain")

    device_slug, device = resolve_device(store, args.device)
    color = resolve_color(device_slug, device, args.color)

    failures = 0
    frames: dict[str, comp.Frame] = {}
    for src in inputs:
        try:
            shot = comp.open_screenshot(src)
            variant = resolve_variant(device_slug, device, color, args.orientation, shot.size)
            screen = variant.effective_screen
            assert screen is not None
            if variant.path not in frames:
                frame_path = store.frame_path(variant)
                if not frame_path.exists():
                    raise CliError(f"frame file missing: {frame_path} (run `frames sync`)")
                frames[variant.path] = comp.Frame.load(frame_path)
            mismatch = comp.aspect_mismatch(shot.size, screen)
            if mismatch > 0.01:
                warn(
                    f"{src.name}: aspect {shot.size[0]}x{shot.size[1]} differs from the {device_slug} "
                    f"{variant.orientation} screen {screen.width}x{screen.height} by {mismatch:.1%}"
                )
            result = frames[variant.path].compose(shot, screen, fit=args.fit, bg=args.bg)
            dest = output_path(src, args.input, args.output, batch)
            dest.parent.mkdir(parents=True, exist_ok=True)
            result.save(dest, "PNG")
            print(f"{src} -> {dest}")
        except (CliError, OSError, ValueError) as exc:
            failures += 1
            print(f"error: {src}: {exc}", file=sys.stderr)
            if not batch:
                return 1
    return 1 if failures else 0


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #


def cmd_list(args: argparse.Namespace, store: Store) -> int:
    if not store.devices:
        print("No frames installed. Run `device-framer frames discover` to see what Apple offers.")
        return 0
    for slug in sorted(store.devices):
        entry = store.devices[slug]
        print(f"{slug}  ({entry.name})")
        for v in entry.variants:
            screen = v.effective_screen
            geom = str(screen) if screen else "screen: undetected"
            override = "  (override)" if v.screen_override else ""
            missing = "" if store.frame_path(v).exists() else "  [missing: run `frames sync`]"
            print(f"  {v.color:<16} {v.orientation:<10} {geom}{override}{missing}")
    return 0


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    g, rest = frames_dir_parent().parse_known_args(argv)

    try:
        if rest and rest[0] in SUBCOMMANDS:
            sub, sub_args = rest[0], rest[1:]
            if sub == "list":
                args = build_list_parser().parse_args(sub_args)
                return cmd_list(args, Store.open(args.frames_dir or g.frames_dir or default_frames_dir()))
            from .frames import run_frames

            return run_frames(sub_args, g.frames_dir)
        args = build_frame_parser().parse_args(argv)
        return cmd_frame(args, Store.open(args.frames_dir or default_frames_dir()))
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
