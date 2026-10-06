# device-framer

CLI that composites screenshots into Apple bezel PNGs. Code in `src/device_framer/`,
tests in `tests/` (run `uv run pytest`; `uv run mypy src` for types). The seam under
test is the CLI invoked in-process with `--frames-dir`; tests build synthetic frames
and real DMGs, never Apple assets.

## Adding a device ("add the iPhone 18 frames")

Everything runs non-interactively; stdin is not a terminal here, so pickers are
unavailable and the flags below are required.

1. **Discover.** `uv run device-framer frames discover` prints bezel DMGs not yet in
   `devices.json`. If it reports zero results, build the URL yourself:
   `https://devimages-cdn.apple.com/design/resources/download/Bezel-<Name-With-Hyphens>.dmg`.
2. **See what is inside.** Run `uv run device-framer frames add "<name>"` with no
   selection flags. It fails on purpose and lists every raw PNG filename in the DMG.
   Only PNGs matter; ignore PSD/Keynote files.
3. **Add the variants the user asked for.**
   `uv run device-framer frames add "<name>" --variants "<raw>,<raw>"`
   (or `--all`). Raw names are Apple's filenames, `Device - Color - Orientation.png`;
   the orientation part may be absent (defaults to portrait). The device slug comes
   from the first part, so one DMG can create several devices.
   Re-adding replaces that device's variant list, so to extend a device include the
   already-installed raw names (read them from `devices.json`).
4. **Verify geometry.** `frames add` prints `screen WxH at X,Y` per variant. Compare
   against the device's known screen resolution; the detected size should match it
   or be within a few pixels. `UNDETECTED` or a wildly off size means the alpha
   channel confused the detector: set `screen_override` on that variant in
   `devices.json`, and report it.
5. **Test render.** Make a solid screenshot at the detected screen size and frame it:
   ```
   uv run python -c "from PIL import Image; Image.new('RGB',(W,H),(200,30,90)).save('/tmp/df-test.png')"
   uv run device-framer /tmp/df-test.png --device <slug> --color <color> -o /tmp/df-test-framed.png
   ```
   Open the output (Read tool) and confirm the colour fills the screen, the bezel is
   intact, and corners/notch mask correctly. No aspect warning should print.
6. **Report.** List each device slug, its colours and orientations, and the detected
   screen sizes. Commit `devices.json` only; `frames/` is gitignored and must stay so.

## Conventions

- Slugs are lowercase hyphenated forms of Apple's names (`iPhone 17 Pro` → `iphone-17-pro`, `Deep Blue` → `deep-blue`). Slug quirks are fixed in `slugs.py`; the manifest keeps raw filenames so nothing needs re-downloading.
- Tests that need `hdiutil` carry `@requires_hdiutil`; keep new DMG-backed tests on the module-scoped `dmg` fixture, since building a DMG is slow.
- Network access is only `frames discover`, `frames add` and `frames sync`. Tests point `DEVICE_FRAMER_RESOURCES_URL` at a local file and use local `.dmg` paths; never hit Apple from a test.
