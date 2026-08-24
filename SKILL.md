---
name: appletv-remote
description: Control an Apple TV over the local network — play movies/shows/YouTube by name, launch apps, navigate, type, play/pause, power. Use whenever the user asks to watch something, put a video on the TV, open an app on the Apple TV, control playback, or mentions Apple TV, the living room TV, or tvOS.
---

# Apple TV Remote

Control an Apple TV on the local network. No server, no daemon: every
action is a one-shot CLI call that connects, acts, and disconnects
(~3–8 seconds). Built on pyatv (Companion + AirPlay protocols).

## Running commands

```bash
uv run <skill-dir>/scripts/atv.py <command>
```

`<skill-dir>` is the directory containing this SKILL.md. Dependencies
are declared inline (PEP 723); `uv run` resolves them automatically.

**Prerequisite:** [uv](https://docs.astral.sh/uv/) must be installed
(`brew install uv`). Nothing else — Python and all libraries come from
`uv run`.

Global flags like `--device <name>` go **before** the subcommand:
`atv.py --device Bedroom playing`.

## Command reference

| Command | What it does |
| --- | --- |
| `scan` | List Apple TVs found on the network |
| `pair [name]` | Register a new TV (see "Registering a TV") |
| `devices` | List paired TVs and which is default |
| `use <name>` | Set the default TV |
| `remote <action>` | Press a button: `up down left right select menu home play pause play_pause stop next previous volume_up volume_down suspend wakeup` |
| `launch <app>` | Open an app: `netflix youtube disney+ max hulu prime video peacock paramount+ plex spotify tv music settings app store` (or a bundle id) |
| `open <url>` | Open a deep link — the way to pull up a *specific* title |
| `watch <title> [--service S]` | Search JustWatch for the title and pull it up (optionally on a specific service, e.g. `--service "disney+"`) |
| `youtube <url\|id\|search terms>` | Play a YouTube video in the system player (resolves search terms itself) |
| `youtube <query> --app` | Open the video in the YouTube app instead |
| `play <url>` | Play ANY video URL: direct media files (.mp4/.m3u8/...) or a page from ~1800 sites (Vimeo, Dailymotion, Twitch, X, news embeds). No DRM services |
| `type <text>` | Type into the currently focused on-screen field |
| `playing` | What's playing (state, title, position) |
| `power wake\|sleep` | Wake / sleep (HDMI-CEC turns the TV off too) |
| `apps` | List installed apps with bundle ids |

## Recipes

**"Watch <movie/show>"** → `watch "<title>"`. If the user names a
service: `watch "<title>" --service "<service>"`. If it reports the
title isn't on that service, tell the user what it *is* available on
and ask before opening elsewhere.

**"Put <something> on YouTube"** → `youtube "<search terms or URL>"`.
Plays full-screen in the system player. Only use `--app` if the user
explicitly wants the YouTube app UI — tvOS shows an "Open in YouTube"
confirmation that a human must accept with the physical remote.

**"Play this video from <some site>"** → `play "<url>"`. Works for
direct media URLs and any site yt-dlp supports. DRM services (Netflix,
Disney+, Max, ...) cannot be extracted — use `watch`/`open` for those.
Some sites (e.g. Vimeo) block extraction with a 403; if that happens,
tell the user and suggest AirPlaying from their phone/browser instead.

**"Open Netflix / go to Plex"** → `launch <app>`.

**Search inside an app** → `launch <app>`, wait a few seconds, then
`remote` navigation and `type "<query>"` once a search field is
focused. You cannot see the screen, so prefer `watch`/`open` deep
links over blind navigation whenever possible.

**Playback control** → `remote play_pause`, `remote menu` (back),
`remote home`. Check state with `playing`.

## Deep-link catalog (for `open`)

tvOS routes these URLs to the right app. Web share links usually work;
find them via web search or the iOS/macOS app's Share → Copy Link.

| App | Working deep-link shape |
| --- | --- |
| Apple TV+ | `https://tv.apple.com/us/show/<slug>/<umc-id>` (also `/movie/`, `/episode/`) |
| Disney+ | `https://www.disneyplus.com/video/<uuid>` or `/series/<slug>/<id>` |
| Max | `https://play.hbomax.com/page/urn:hbo:page:<id>` |
| Hulu | `https://www.hulu.com/watch/<id>` or `hulu://series/<uuid>` |
| Prime Video | `https://watch.amazon.com/detail?gti=<id>` |
| Peacock | `https://www.peacocktv.com/watch/playback/vod/<id>` |
| YouTube | `youtube://www.youtube.com/watch?v=<id>` (may prompt) |
| Netflix | `https://www.netflix.com/title/<id>` — **unreliable**; broke in a Sept 2025 app update. Fall back to `launch netflix` + `type` |

## Registering a TV (required once per TV)

Pairing stores credentials in `~/.config/appletv-remote/devices.json`.
It pairs both the Companion protocol (apps, keyboard, deep links) and
AirPlay (video push). The TV shows a 4-digit PIN for each.

**For a human at a terminal** (e.g. after distributing this skill):

```bash
uv run <skill-dir>/scripts/atv.py pair
```

It scans, lists devices, asks which to pair, and prompts for each PIN.
The first paired TV becomes the default; change with `use <name>`.

**For an agent driving it** (no interactive stdin):

```bash
export ATV_PIN_FILE=/tmp/atv_pin.txt
uv run <skill-dir>/scripts/atv.py pair "Living Room" &   # name filter REQUIRED
# ask the user for the PIN on screen, then:
echo 1234 > /tmp/atv_pin.txt     # repeat for the second PIN (AirPlay)
```

Requirements: Mac and Apple TV on the same network; the TV awake.
tvOS 13+ works; tested on tvOS 26.

**Keep `devices.json` private.** It holds the pairing credentials —
anyone with that file plus network access to the TV controls it. Never
commit it, paste it, or include it when distributing this skill. The
file is written owner-only (0600).

## Rules and gotchas

- **Never blind-press `select`** (or any button) to "confirm a dialog" —
  you cannot see the screen. A stray press can launch whatever tile has
  focus. Deep links either work or they don't; report and move on.
- `watch` uses JustWatch's unofficial API; if it returns nothing, fall
  back to finding a deep link via web search + `open`, or
  `launch` + `type`. Region defaults to US/en — override with
  `ATV_JW_COUNTRY` / `ATV_JW_LANGUAGE` env vars.
- `youtube` (without `--app`) and `play` stream via AirPlay 2: playback
  is queued on the TV and continues after the command exits. Stream
  URLs expire after ~6 hours and are IP-bound — resolve fresh each time.
- A `FetchAttentionState failed` warning at connect time is benign
  (fork quirk); commands still work.
- The pyatv dependency is pinned to an unmerged fork fixing `play_url`
  on tvOS 26 (upstream PR #2846). Once that merges and releases, switch
  the pin in `scripts/atv.py` back to stock `pyatv>=0.19`.
- If commands suddenly fail with auth errors (e.g. after a tvOS update
  or Home key reset), re-run `pair`.
