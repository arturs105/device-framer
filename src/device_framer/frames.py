"""The ``frames`` subcommand group: discover, add, sync, remove."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from PIL import Image

from .cli import frames_dir_parent
from .console import PROG, USER_AGENT, CliError, is_interactive, warn
from .geometry import detect_screen
from .manifest import DeviceEntry, Store, Variant, default_frames_dir
from .slugs import ParsedName, bezel_urls, display_name_from_url, parse_png_name, slugify

RESOURCES_URL = "https://developer.apple.com/design/resources/"
BEZEL_URL_TEMPLATE = "https://devimages-cdn.apple.com/design/resources/download/Bezel-{}.dmg"


def resources_url() -> str:
    return os.environ.get("DEVICE_FRAMER_RESOURCES_URL", RESOURCES_URL)


# --------------------------------------------------------------------------- #
# Network / DMG plumbing
# --------------------------------------------------------------------------- #


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(_request(url), timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")  # type: ignore[no-any-return]


def is_url(text: str) -> bool:
    return urlparse(text).scheme in {"http", "https", "file"}


def download(url: str, dest_dir: Path) -> Path:
    """Download (or copy, for local paths / file URLs) a DMG into ``dest_dir``."""
    parsed = urlparse(url)
    dest = dest_dir / (Path(parsed.path).name or "bezel.dmg")
    if parsed.scheme == "file":
        shutil.copy(urllib.request.url2pathname(parsed.path), dest)
    elif parsed.scheme in {"http", "https"}:
        print(f"Downloading {url} ...")
        try:
            with urllib.request.urlopen(_request(url), timeout=120) as resp, dest.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
        except (urllib.error.URLError, OSError) as exc:
            raise CliError(f"download failed for {url}: {exc}") from exc
    else:
        src = Path(url).expanduser()
        if not src.is_file():
            raise CliError(f"DMG not found: {url}")
        shutil.copy(src, dest)
    return dest


@dataclass
class Candidate:
    """A PNG inside a mounted DMG."""

    path: Path
    parsed: ParsedName

    @property
    def raw(self) -> str:
        return self.path.name


class MountedDmg:
    """Context manager: ``hdiutil attach`` read-only, detach on exit."""

    def __init__(self, dmg: Path) -> None:
        self.dmg = dmg
        self.mountpoint: Path | None = None

    def __enter__(self) -> "MountedDmg":
        if shutil.which("hdiutil") is None:
            raise CliError("hdiutil not found; device-framer only supports macOS for DMG extraction")
        tmp = Path(tempfile.mkdtemp(prefix="device-framer-mnt-"))
        proc = subprocess.run(
            ["hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen", "-noverify", "-mountpoint", str(tmp), str(self.dmg)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise CliError(f"could not mount {self.dmg.name}: {proc.stderr.strip()}")
        self.mountpoint = tmp
        return self

    def __exit__(self, *exc: object) -> None:
        if self.mountpoint is None:
            return
        proc = subprocess.run(["hdiutil", "detach", "-quiet", str(self.mountpoint)], capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(["hdiutil", "detach", "-force", "-quiet", str(self.mountpoint)], capture_output=True)
        shutil.rmtree(self.mountpoint, ignore_errors=True)

    def candidates(self) -> list[Candidate]:
        assert self.mountpoint is not None
        pngs = sorted(p for p in self.mountpoint.rglob("*.png") if not p.name.startswith("._"))
        return [Candidate(p, parse_png_name(p.name)) for p in pngs]


# --------------------------------------------------------------------------- #
# discover
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Bezel:
    name: str
    url: str


def discover_bezels() -> list[Bezel]:
    url = resources_url()
    try:
        html = fetch_text(url)
    except Exception as exc:  # network / parse failures must never traceback
        warn(f"could not fetch {url}: {exc}")
        return []
    return [Bezel(display_name_from_url(u), u) for u in bezel_urls(html)]


def cmd_discover(args: argparse.Namespace, store: Store) -> int:
    url = resources_url()
    print(f"Source: {url}")
    bezels = discover_bezels()
    if not bezels:
        print("No bezel DMGs found. Apple may have changed the page markup.")
        print(f"You can still add one directly: {PROG} frames add <dmg-url>")
        return 0
    known = {d.dmg_url for d in store.devices.values()}
    missing = [b for b in bezels if b.url not in known]
    if not missing:
        print(f"All {len(bezels)} bezel DMGs are already in the manifest.")
        return 0
    print(f"{len(missing)} bezel DMG(s) not in your manifest:\n")
    width = max(len(b.name) for b in missing)
    for b in missing:
        print(f"  {b.name:<{width}}  {b.url}")
    print(f'\nAdd one with: {PROG} frames add "<name>"')
    return 0


# --------------------------------------------------------------------------- #
# add
# --------------------------------------------------------------------------- #


def resolve_dmg_source(arg: str) -> str:
    """Turn a discover name, URL or local ``.dmg`` path into something ``download`` accepts."""
    if is_url(arg):
        return arg
    local = Path(arg).expanduser()
    if local.suffix.lower() == ".dmg" and local.is_file():
        return str(local.resolve())
    wanted = slugify(arg)
    for b in discover_bezels():
        if slugify(b.name) == wanted:
            return b.url
    raise CliError(
        f"'{arg}' is not a bezel listed by `frames discover`, a URL or a local .dmg.\n"
        f"Apple bezel URLs look like {BEZEL_URL_TEMPLATE.format('iPhone-17')}"
    )


def _norm(name: str) -> str:
    name = name.strip().strip('"').strip("'")
    if name.lower().endswith(".png"):
        name = name[:-4]
    return name.casefold()


def select_candidates(candidates: list[Candidate], variants: str | None, select_all: bool, preselected: set[str]) -> list[Candidate]:
    if select_all:
        return candidates
    listing = "\n".join(f"  {c.raw}" for c in candidates)
    if variants:
        by_norm = {_norm(c.raw): c for c in candidates}
        wanted = [_norm(v) for v in variants.split(",") if v.strip()]
        unknown = [w for w in wanted if w not in by_norm]
        if unknown:
            raise CliError("unknown variant(s): " + ", ".join(unknown) + f"\nAvailable variants:\n{listing}")
        return [by_norm[w] for w in wanted]
    if not is_interactive():
        raise CliError(f'no terminal for the picker; pass --variants "<name>,<name>" or --all.\nAvailable variants:\n{listing}')
    try:
        import questionary

        choices = [questionary.Choice(c.raw, value=c, checked=c.raw in preselected) for c in candidates]
        picked = questionary.checkbox("Select the variants to keep (space to toggle, enter to confirm):", choices=choices).ask()
    except Exception as exc:
        raise CliError(f"picker failed ({exc}); pass --variants or --all.\nAvailable variants:\n{listing}") from exc
    if picked is None:
        raise CliError("cancelled")
    return list(picked)


def install_variant(store: Store, cand: Candidate) -> Variant:
    p = cand.parsed
    rel = Path(p.device_slug) / f"{p.color_slug}-{p.orientation_slug}.png"
    dest = store.frames_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(cand.path, dest)
    with Image.open(dest) as img:
        screen = detect_screen(img)
    if screen is None:
        warn(f"{cand.raw}: could not detect a screen cutout; set screen_override in devices.json")
    return Variant(raw=cand.raw, color=p.color_slug, orientation=p.orientation_slug, path=rel.as_posix(), screen=screen)


def cmd_add(args: argparse.Namespace, store: Store) -> int:
    source = resolve_dmg_source(args.source)
    preselected = {v.raw for d in store.devices.values() if d.dmg_url == source for v in d.variants}
    with tempfile.TemporaryDirectory(prefix="device-framer-") as tmp:
        dmg = download(source, Path(tmp))
        with MountedDmg(dmg) as mounted:
            candidates = mounted.candidates()
            if not candidates:
                raise CliError(f"no PNG files found inside {dmg.name}")
            chosen = select_candidates(candidates, args.variants, args.all, preselected)
            if not chosen:
                raise CliError("nothing selected")

            touched: dict[str, list[Variant]] = {}
            names: dict[str, str] = {}
            for cand in chosen:
                variant = install_variant(store, cand)
                touched.setdefault(cand.parsed.device_slug, []).append(variant)
                names[cand.parsed.device_slug] = cand.parsed.device_name
                print(f"  {cand.raw}  ->  {variant.path}  screen {variant.screen or 'UNDETECTED'}")

            for slug, variants in touched.items():
                old = store.devices.get(slug)
                if old:
                    # keep hand-made overrides for variants that survive; drop files that do not
                    overrides = {v.raw: v.screen_override for v in old.variants if v.screen_override}
                    for v in variants:
                        v.screen_override = overrides.get(v.raw)
                    new_paths = {v.path for v in variants}
                    for v in old.variants:
                        if v.path not in new_paths:
                            store.frame_path(v).unlink(missing_ok=True)
                store.devices[slug] = DeviceEntry(
                    name=names[slug], dmg_url=source, variants=variants, default_color=old.default_color if old else None
                )
            store.save()
        dmg.unlink(missing_ok=True)
    print(f"\nUpdated {store.manifest_path} with {len(touched)} device(s): {', '.join(sorted(touched))}")
    return 0


# --------------------------------------------------------------------------- #
# sync
# --------------------------------------------------------------------------- #


def cmd_sync(args: argparse.Namespace, store: Store) -> int:
    missing: dict[str, list[Variant]] = {}
    for entry in store.devices.values():
        for v in entry.variants:
            if not store.frame_path(v).exists():
                missing.setdefault(entry.dmg_url, []).append(v)
    if not missing:
        print("All frames are present; nothing to do (up to date).")
        return 0
    failures = 0
    with tempfile.TemporaryDirectory(prefix="device-framer-") as tmp:
        for url, variants in missing.items():
            try:
                dmg = download(url, Path(tmp))
                with MountedDmg(dmg) as mounted:
                    by_raw = {c.raw.casefold(): c for c in mounted.candidates()}
                    for v in variants:
                        cand = by_raw.get(v.raw.casefold())
                        if cand is None:
                            failures += 1
                            print(f"error: {v.raw} not found in {dmg.name}", file=sys.stderr)
                            continue
                        dest = store.frame_path(v)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(cand.path, dest)
                        print(f"  restored {v.path}")
                dmg.unlink(missing_ok=True)
            except CliError as exc:
                failures += len(variants)
                print(f"error: {url}: {exc}", file=sys.stderr)
    return 1 if failures else 0


# --------------------------------------------------------------------------- #
# remove
# --------------------------------------------------------------------------- #


def cmd_remove(args: argparse.Namespace, store: Store) -> int:
    slug = args.device
    if slug not in store.devices:
        raise CliError(f"unknown device '{slug}'. Installed devices: " + (", ".join(sorted(store.devices)) or "(none)"))
    entry = store.devices[slug]
    if not args.yes:
        if not is_interactive():
            raise CliError(f"refusing to remove {slug} without confirmation; pass --yes")
        import questionary

        if not questionary.confirm(f"Remove {slug} ({len(entry.variants)} variant(s)) and its frames?", default=False).ask():
            print("cancelled")
            return 1
    shutil.rmtree(store.frames_dir / slug, ignore_errors=True)
    del store.devices[slug]
    store.save()
    print(f"Removed {slug}")
    return 0


# --------------------------------------------------------------------------- #
# Parser / dispatch
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    common = [frames_dir_parent()]
    p = argparse.ArgumentParser(
        prog=f"{PROG} frames",
        description="Manage the local library of Apple bezel PNGs.",
        epilog=(
            "examples:\n"
            f"  {PROG} frames discover\n"
            f'  {PROG} frames add "iPhone 17"\n'
            f'  {PROG} frames add "iPhone 17" --variants "iPhone 17 Pro - Deep Blue - Portrait.png"\n'
            f"  {PROG} frames add https://devimages-cdn.apple.com/design/resources/download/Bezel-iPad-Pro-M5.dmg --all\n"
            f"  {PROG} frames sync\n"
            f"  {PROG} frames remove iphone-17-pro --yes\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=common,
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    d = sub.add_parser(
        "discover",
        help="list Apple bezel DMGs that are not in the manifest yet",
        description="Fetch Apple's design resources page and list bezel DMGs not yet in devices.json.",
        parents=common,
    )
    d.set_defaults(func=cmd_discover)

    a = sub.add_parser(
        "add",
        help="download a bezel DMG and keep selected PNG variants",
        description="Download a bezel DMG, pick PNG variants (checkbox picker, --variants or --all), copy them into frames/ and record them in devices.json.",
        epilog=(
            "examples:\n"
            f'  {PROG} frames add "iPhone 17"\n'
            f'  {PROG} frames add "iPhone 17" --variants "iPhone 17 Pro - Deep Blue - Portrait.png,iPhone 17 Pro - Deep Blue - Landscape.png"\n'
            f"  {PROG} frames add ~/Downloads/Bezel-iPhone-17.dmg --all\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=common,
    )
    a.add_argument("source", help="name as shown by `frames discover`, a DMG URL, or a local .dmg path")
    a.add_argument("--variants", help="comma-separated raw PNG filenames to keep (non-interactive)")
    a.add_argument("--all", action="store_true", help="keep every PNG in the DMG (non-interactive)")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser(
        "sync",
        help="re-download frames listed in the manifest that are missing locally",
        description="Restore every manifest variant whose PNG is missing. Never prompts.",
        parents=common,
    )
    s.set_defaults(func=cmd_sync)

    r = sub.add_parser(
        "remove",
        help="delete a device's frames and manifest entry",
        description="Delete frames/<device>/ and the device's entry in devices.json.",
        parents=common,
    )
    r.add_argument("device", help="device slug (see `list`)")
    r.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    r.set_defaults(func=cmd_remove)
    return p


def run_frames(argv: Sequence[str], frames_dir: Path | None) -> int:
    args = build_parser().parse_args(list(argv))
    store = Store.open(args.frames_dir or frames_dir or default_frames_dir())
    return int(args.func(args, store))
