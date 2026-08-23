---
name: pygame-headless-test-and-release
description: Use when testing, running, or screenshotting a pygame/SDL app without a display (CI, agent sandbox, SSH session), when pygame.init fails with "No available video device", or when cutting a GitHub release for a pygame project
---

# Pygame Headless: Test, Run, Release

## Overview

pygame (SDL) refuses to start without a display. The dummy drivers make every pygame codepath — tests, CLI subcommands, even frame rendering — work headless.

## Headless testing

Set the drivers in `tests/conftest.py` BEFORE pygame is imported, with `setdefault` so a real display still wins locally:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
```

Same trick for one-off CLI runs:

```sh
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python game.py --list-players
```

Audio matters too — `SDL_AUDIODRIVER=dummy` prevents ALSA/Pulse errors on machines with no sound stack (CI containers).

## Screenshots

- **Headless**: the dummy video driver still renders — you still call `pygame.display.set_mode(...)` to get a surface, then `pygame.image.save(screen, "shot.png")` works with no display at all. Drive the game loop a few frames first, and give the app a trigger (a `--screenshot PATH` flag or test fixture) so CI can invoke it.
- **Real display on Wayland/X11**: no single screenshot tool is universal. Probe in order and use the first present:
  ```sh
  for t in grim scrot maim import; do command -v "$t" && break; done
  ```
  (`grim` = Wayland, `scrot`/`maim` = X11, `import` = ImageMagick fallback.)

## Release loop

1. Run the tests headless (above) — green before tagging.
2. If the app writes user data (save files, `profiles.json`), **back it up before exercising destructive CLI flags** (`--reset`, `--delete-player`) in pre-release testing.
3. Tag and release, verifying the tag actually exists at the remote:
   ```sh
   git tag -a v1.2.0 -m "v1.2.0" && git push origin v1.2.0
   gh release create v1.2.0 --verify-tag --generate-notes
   ```
   `--verify-tag` fails fast if the tag never got pushed — better than a release pointing at nothing.

## Common mistakes

- Setting `SDL_VIDEODRIVER` after `import pygame` + `pygame.init()` — too late; the driver is chosen at init.
- Using `os.environ[...] = "dummy"` (hard assignment) in conftest — breaks running the same tests on a machine with a display when you *want* to watch.
- Forgetting the audio driver — video works, then CI dies on ALSA errors.
- Testing destructive CLI flags against the only copy of real save data.
