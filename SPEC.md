# device-framer — Specification

Status: ready-for-agent
Date: 2026-10-06

## Problem Statement

I regularly take screenshots of apps running on iPhone, iPad, Mac, Apple Watch and Apple TV and want them presented inside the official Apple device bezels for docs, App Store marketing, blog posts and decks. Today that means opening Photoshop or Figma, dragging the screenshot into the right layer, aligning it, exporting and repeating for every screenshot and every device. Apple also releases new bezels every year, so whatever I use must let me add new devices with almost no effort, ideally by just telling an agent "add the iPhone 18 frames".

## Solution

A macOS command line tool, `device-framer`, that composites one image or a folder of images into an Apple product bezel PNG and writes framed PNGs next to the inputs. Device and colour are chosen with flags or an arrow-key picker. Frames are not shipped with the tool; a `frames` subcommand group downloads Apple's bezel DMGs on demand, lets me pick exactly the colours and orientations I want, keeps only those PNGs locally, and records the choice in a committed manifest so a fresh clone can restore them. A `CLAUDE.md` describes the add-a-device procedure so an agent can do it end to end using non-interactive flags.

## User Stories

### Framing

1. As a user, I want to run `device-framer shot.png --device iphone-17-pro --color deep-blue`, so that I get `shot-framed.png` next to the input with the screenshot inside the bezel.
2. As a user, I want to pass a folder instead of a file, so that every supported image in it is framed in one run.
3. As a user, I want `-r` to recurse into subfolders, so that I can batch an entire screenshots tree.
4. As a user, I want png, jpg, jpeg, webp and heic inputs accepted, so that raw simulator, device and browser screenshots all work without conversion.
5. As a user, I want `-o <dir>` on batch runs and `-o <file>` on single runs, so that I control where output goes.
6. As a user, I want output written at the frame's native pixel size as a PNG with a transparent background outside the device, so that I can drop it onto any backdrop without quality loss.
7. As a user, I want existing output files overwritten silently, so that re-running after a screenshot changes is frictionless.
8. As a user, I want the screenshot scaled to fill the screen cutout and centre-cropped, so that a slightly off-size screenshot still looks right.
9. As a user, I want a warning when the input aspect ratio differs from the screen cutout by more than roughly 1 percent, so that I notice when I picked the wrong device.
10. As a user, I want `--fit contain --bg <color>` as an alternative, so that nothing is cropped when I prefer letterboxing.
11. As a user, I want the screen area clipped by the frame's transparency, so that rounded corners, the notch, the Dynamic Island and round Watch faces mask the screenshot correctly.
12. As a user, I want orientation picked automatically from the input image's aspect ratio among installed variants, so that I don't specify portrait or landscape for every file.
13. As a user, I want `--orientation` to override that choice, so that I can force a variant when the heuristic is wrong.
14. As a user, I want to be prompted for orientation only when no installed variant matches the input aspect, so that the tool never guesses blindly.

### Choosing device and colour

15. As a user, I want an arrow-key picker for device and then colour when I omit the flags, so that I don't have to remember slugs.
16. As a user, I want the picker shown once per run for a batch, so that the same device and colour applies to the whole folder.
17. As a user, I want the tool to fail fast with the list of valid devices and colours when flags are missing and stdin is not a terminal, so that scripts and agents never hang.
18. As a user, I want `device-framer list` to print installed devices with their colours, orientations and detected screen sizes, so that I know what I can use.
19. As a user, I want a clear error naming the valid colours when I pass a colour that is not installed for the chosen device, so that I can fix the command quickly.

### Managing frames

20. As a user, I want `device-framer frames discover` to fetch Apple's design resources page and list bezel DMGs that are not in my manifest, so that I learn about new devices without browsing.
21. As a user, I want `frames discover` to print the page URL and report zero results gracefully if Apple changes the markup, so that a scrape failure never blocks me.
22. As a user, I want `device-framer frames add <name|url>` to accept either a name as shown by discover or a raw DMG URL, so that I can add a device even when discover fails.
23. As a user, I want `frames add` to download the DMG, mount it, show a checkbox picker of the PNG variants inside using Apple's raw filenames, so that I only keep the colours and orientations I actually use.
24. As a user, I want `frames add --variants "<raw name>,<raw name>"` and `--all` as non-interactive alternatives, so that an agent or script can add frames without the picker.
25. As a user, I want the chosen PNGs copied into `frames/<device-slug>/<color-slug>-<orientation>.png`, the DMG detached and deleted, so that no disk space is wasted on DMGs or unused colours.
26. As a user, I want the screen geometry detected from each frame's alpha channel and stored in the manifest when a frame is added, so that no manual coordinates are ever needed.
27. As a user, I want `frames add` to print the detected screen size per variant, so that I or an agent can verify it looks plausible.
28. As a user, I want a manifest override field for screen geometry, so that a mis-detected cutout can be corrected by hand.
29. As a user, I want the manifest to record the DMG URL, the raw-filename to slug mapping and the chosen variants, so that the choice is reproducible and slug quirks are fixable.
30. As a user, I want `device-framer frames sync` to re-download and extract every manifest variant that is missing locally without prompting, so that a fresh clone becomes usable with one command.
31. As a user, I want `device-framer frames remove <device>` to delete the device's frames and manifest entry, so that I can clean up devices I no longer use.
32. As a user, I want the `frames/` folder gitignored and the manifest committed, so that Apple's assets are never pushed to a repository.
33. As a user, I want re-adding an existing device to let me extend or replace the chosen variants, so that adding one more colour later is easy.

### Help and agent workflow

34. As a user, I want `-h` and `--help` to explain the workflow with examples for framing, listing and every `frames` subcommand, so that I can use the tool without reading the README.
35. As a user, I want each subcommand to have its own `--help`, so that flags are discoverable in context.
36. As a Claude Code agent, I want a `CLAUDE.md` describing how to discover, add with `--variants`, test-render and report detected screen sizes, so that I can add a new device end to end when the user asks.
37. As a user, I want a README covering install, usage and the licensing note about Apple assets, so that others can use the tool.
38. As a user, I want the tool installable with `uv tool install .` or `pipx install .`, so that `device-framer` is on my PATH.

## Implementation Decisions

- **Language and dependencies.** Python 3.12 or newer, Pillow for imaging, `questionary` for the arrow-key single-select and checkbox pickers, `pillow-heif` as an optional extra for HEIC input. Standard library `urllib` for HTTP and `subprocess` for `hdiutil`. No other runtime dependencies.
- **Packaging.** A `pyproject.toml` with a single package and a `device-framer` console script entry point. Tests via pytest.
- **Platform.** macOS only. DMG mounting uses `hdiutil attach` / `hdiutil detach`; no Linux fallback.
- **CLI shape.** Top-level positional input performs framing. Subcommands: `list`, `frames discover`, `frames add`, `frames sync`, `frames remove`. Flags for framing: `--device`, `--color`, `--orientation`, `--fit {cover,contain}`, `--bg`, `-o`, `-r`. Flags for `frames add`: `--variants`, `--all`. A global `--frames-dir` flag and `DEVICE_FRAMER_HOME` environment variable override the frames root and manifest location; default is the `frames/` folder and `devices.json` beside it at the project root.
- **Frame storage.** `frames/<device-slug>/<color-slug>-<orientation>.png`. Slugs are lowercase, hyphen-separated, derived from Apple's PNG filenames by splitting on the ` - ` separator into device, colour and orientation parts; orientation defaults to `portrait` when absent. The folder is gitignored.
- **Manifest schema (`devices.json`).** Top-level map of device slug to an entry containing: display name, DMG URL, list of variants. Each variant records the raw Apple filename, colour slug, orientation, local relative path, detected screen geometry (x, y, width, height) and an optional `screen_override` with the same shape that takes precedence. A `default_color` per device is optional.
- **Geometry detection.** The screen region is the bounding box of fully transparent pixels inside the frame PNG's alpha channel, excluding transparent margins outside the device silhouette by taking the largest transparent connected region that is enclosed by opaque pixels. The alpha channel inside that bounding box is inverted and used as the paste mask so corner radii, notches and round faces clip the screenshot.
- **Compositing.** Convert input to RGBA, resize to cover (or contain) the screen box using Lanczos resampling, centre it, paste through the mask onto a transparent canvas the size of the frame, then alpha-composite the frame on top. Output is PNG at frame size.
- **Device and colour resolution.** Flags are matched against manifest slugs. Missing flags trigger the picker when stdin and stdout are TTYs; otherwise the command exits non-zero and prints the valid values. Orientation is auto-chosen by comparing the input aspect to each installed variant's screen box aspect; ties or no match fall back to the picker or an error under non-TTY.
- **Batch semantics.** Folder input collects files with supported extensions, sorted, non-recursive unless `-r`. One device and colour resolution per run. Each file is framed independently and failures are reported per file while the run continues; exit code is non-zero if any file failed.
- **Discover.** Fetch `https://developer.apple.com/design/resources/`, regex all `https://devimages-cdn.apple.com/design/resources/download/Bezel-*.dmg` links, derive a display name from the filename, diff against manifest URLs, print missing ones. Zero matches prints the URL and a hint.
- **Add.** Resolve the argument to a URL (exact discover name, case-insensitive match, or raw URL; a local `.dmg` path is also accepted, which is what tests use). Download to a temporary directory, mount read-only, enumerate PNGs recursively, present the checkbox picker or apply `--variants`/`--all`, copy the chosen PNGs into place, detect geometry, update the manifest, detach, delete the temporary DMG. Re-adding an existing device pre-selects already installed variants in the picker and replaces the variant list with the new selection.
- **Sync.** For each manifest variant whose local file is missing, download and mount the DMG once per device and copy only the missing raw filenames. Never prompts.
- **Remove.** Delete the device folder and manifest entry; confirm in the picker when run interactively, `--yes` to skip.
- **Agent instructions.** `CLAUDE.md` documents the add procedure using non-interactive flags and tells the agent to run a test render against a sample screenshot and report detected screen sizes.
- **Licensing.** MIT for the code. README and LICENSE note that Apple bezel assets are not included and are subject to Apple's terms.

## Testing Decisions

- **Seam.** The single seam is the CLI entry point invoked in-process with an argument list, a temporary frames root passed via `--frames-dir`, and non-TTY stdin so pickers never appear. Tests assert on exit codes, printed output, files written and manifest contents. No internal functions are tested directly except the geometry detector, which gets a focused unit test because its edge cases are easiest to express on tiny synthetic images.
- **Fixtures.** No Apple assets in the repo. Tests generate synthetic frame PNGs with Pillow: an opaque rounded rectangle with a transparent screen cutout, including a notch-like opaque intrusion and a round-face variant. For `add` and `sync`, tests build a real DMG with `hdiutil create` from a folder of synthetic PNGs named in Apple's `Device - Color - Orientation.png` style, so mounting, enumeration and cleanup are exercised for real. These tests are skipped when `hdiutil` is unavailable.
- **What a good test looks like.** It runs a command a user would run and checks what the user would observe: the output file exists at the expected path, its size equals the frame size, the pixel at the screen centre comes from the screenshot, the pixel in a notch region comes from the frame, the manifest lists the chosen variants, the DMG is gone afterwards. Tests never assert on internal data structures or call order.
- **Coverage targets.** Framing single file and folder, recursion, output flag, cover vs contain, aspect warning, orientation auto-pick and override, missing flags under non-TTY, invalid colour error, `list`, `add` with `--variants` and `--all`, re-add replacing variants, `sync` restoring missing files, `remove`, `discover` against a stubbed HTML page served from a local file or patched fetch, help output containing examples.
- **Prior art.** None; the repository is new.

## Out of Scope

- Any background colour, shadow, padding or `--width` downscaling of the output.
- Linux or Windows support, including 7z-based DMG extraction.
- Photoshop or Keynote assets in the DMGs; only PNGs are used.
- Automatic device detection from screenshot resolution.
- Non-Apple device frames or user-supplied frame PNGs outside the Apple DMG workflow.
- Committing any Apple asset to the repository.
- GUI, web interface or watch-folder mode.

## Further Notes

- Apple's bezel DMG URLs follow the pattern `https://devimages-cdn.apple.com/design/resources/download/Bezel-<Device>.dmg` and require no sign-in as of 2026-10-06. Devices currently listed: iPhone 16, 17, 18 and Duo; iPad (A16), iPad Air (M4), iPad mini (A17 Pro), iPad Pro (M5); MacBook Air M5, MacBook Pro M5, MacBook Neo, iMac, Studio Displays; Apple Watch Series 11, Ultra 2, Ultra 3; Apple TV.
- The exact layout and naming of PNGs inside the DMGs has not been inspected yet. The first `frames add` run should be used to confirm the ` - ` separator assumption and adjust the slug parser if needed; the manifest keeps raw filenames precisely so this can be corrected without re-downloading.
- Pickers come from `questionary`, which raises when no TTY is present; the tool catches that and prints the valid values instead of a traceback.
