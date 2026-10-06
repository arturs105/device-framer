# device-framer

Composite iPhone, iPad, Mac, Apple Watch and Apple TV screenshots into Apple's
official device bezels from the command line. macOS only.

```
device-framer shot.png --device iphone-17-pro --color deep-blue
# -> shot-framed.png, a transparent PNG at the bezel's native size
```

Frames are not shipped with the tool. `device-framer frames add` downloads the
bezel DMG from Apple's Design Resources, lets you keep only the colours and
orientations you use, and records that choice in a committed `devices.json`
so `frames sync` can restore them on a fresh clone. The `frames/` folder itself
is gitignored.

## Install

Requires macOS (for `hdiutil`) and Python 3.12+.

```
uv tool install .          # or: pipx install .
uv tool install '.[heic]'  # adds HEIC input support via pillow-heif
```

For development: `uv sync --all-groups && uv run pytest`.

## Usage

```
device-framer <file|folder> [--device SLUG] [--color SLUG] [--orientation NAME]
                            [--fit cover|contain] [--bg COLOR] [-o PATH] [-r]
device-framer list
device-framer frames discover
device-framer frames add <name|url|path.dmg> [--variants "A.png,B.png" | --all]
device-framer frames sync
device-framer frames remove <device> [--yes]
```

Framing:

- Input may be a file or a folder (`-r` recurses). png, jpg, jpeg, webp and heic are accepted.
- Output is `<name>-framed.png` beside each input, or under `-o` (a file for single input, a directory for folders). Existing files are overwritten.
- The screenshot is scaled to cover the screen cutout and centre-cropped; `--fit contain --bg '#000'` letterboxes instead. A warning is printed when the aspect ratio differs from the screen by more than 1%.
- Orientation is picked from the input's aspect among installed variants; `--orientation` overrides it.
- Omit `--device`/`--color` for an arrow-key picker. Without a terminal the command exits non-zero and prints the valid values, so scripts never hang.

Frames:

1. `frames discover` lists bezel DMGs on Apple's page that are not yet in your manifest.
2. `frames add "iPhone 17"` downloads the DMG, mounts it, and shows a checkbox picker of the PNGs inside using Apple's raw filenames. `--variants "<raw>,<raw>"` or `--all` skip the picker. Chosen PNGs land in `frames/<device>/<color>-<orientation>.png`; the DMG is detached and deleted. One DMG can produce several devices (e.g. iPhone 17 and iPhone 17 Pro).
3. Screen geometry is detected from each frame's alpha channel and printed. If a detection looks wrong, add `"screen_override": {"x":…, "y":…, "width":…, "height":…}` to that variant in `devices.json`.
4. Re-running `frames add` for a DMG pre-selects installed variants and replaces the device's variant list with the new selection.
5. `frames sync` restores missing frames without prompting. `frames remove <device>` deletes a device.

Files already named `*-framed.*` are skipped when framing a folder, so re-running
on the same folder does not frame earlier outputs.

Frames root: `--frames-dir`, else `$DEVICE_FRAMER_HOME/frames`, else the
`frames/` folder of this checkout. When installed as a tool outside a checkout
it falls back to `~/.device-framer/frames`; set `DEVICE_FRAMER_HOME` to point
it at a clone whose `devices.json` you commit. `devices.json` always sits
beside the frames folder.

## Adding a new device with an agent

`CLAUDE.md` describes the non-interactive procedure. In short: "add the iPhone 18 frames".

## Licensing

The code is MIT licensed. Apple's bezel artwork is **not** included and is
subject to [Apple's terms](https://developer.apple.com/design/resources/);
never commit the `frames/` folder or redistribute the PNGs.
