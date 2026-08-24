# appletv-remote

A Claude Code / opencode **skill** that gives your AI agent full control
of an Apple TV over the local network — no remote, no Siri, no server.

Tell your agent "pull up Severance" or "put the Veritasium video on the
living room TV" and it just happens. Built on
[pyatv](https://github.com/postlund/pyatv) (Companion + AirPlay
protocols). A sibling project,
[appletv-mcp](https://github.com/slandau3/appletv-mcp), provides the
same capabilities as an MCP server instead of a skill.

## What it can do

- **"Watch \<movie/show\>"** — JustWatch search → deep link straight
  into the title (Apple TV+, Disney+, Max, Hulu, Prime, Peacock, …)
- **"Put \<anything\> on YouTube"** — resolves search terms with yt-dlp,
  plays full-screen via AirPlay (optionally inside the YouTube app)
- **"Play this video"** from almost any site — `play <url>` handles
  direct media files (.mp4/.m3u8) and ~1,800 sites via yt-dlp (Vimeo,
  Dailymotion, Twitch, X, news embeds). No DRM services
- **Full remote** — navigation, select, menu, home, play/pause, volume,
  sleep/wake (HDMI-CEC turns the TV off too)
- **Apps** — launch by friendly name, list installed apps
- **Keyboard** — type into focused on-screen fields
- **Deep links** — open any URL; tvOS routes it to the right app
- **Multi-TV** — pair several, pick a default, target with `--device`

No daemon: every action is a one-shot CLI call that connects, acts, and
disconnects.

## Install

1. **Prerequisite:** [uv](https://docs.astral.sh/uv/) (`brew install uv`).
   Everything else (Python, pyatv, yt-dlp) is resolved by `uv run` from
   the script's inline dependencies.

2. **Copy the skill folder** where your agent loads skills:

   ```bash
   git clone https://github.com/slandau3/appletv-remote.git
   cp -r appletv-remote ~/.claude/skills/appletv-remote   # Claude Code + opencode
   ```

3. **Pair your TV** (once per TV; the TV shows a 4-digit PIN twice):

   ```bash
   uv run ~/.claude/skills/appletv-remote/scripts/atv.py pair
   ```

   Credentials are stored owner-only (0600) in
   `~/.config/appletv-remote/devices.json`. Keep that file private —
   it grants full control of the TV, and it is **not** part of this
   repo.

Restart your agent; it will pick up the skill automatically.

## Usage (what the agent runs)

```
atv.py watch "severance" [--service "disney+"]   # find + pull up a title
atv.py youtube "veritasium" [--app]              # play YouTube (or in-app)
atv.py play <url>                                # any video URL / site
atv.py launch netflix                            # open an app
atv.py open <deep-link-url>                      # route any URL to its app
atv.py remote up|down|...|select|menu|home|play_pause|volume_up|suspend|...
atv.py type "search text"                        # type into focused field
atv.py playing                                   # what's on now
atv.py power wake|sleep
atv.py apps | devices | scan | use <name> | pair [name]
```

Global flags like `--device <name>` go **before** the subcommand.

## Notes and caveats

- **pyatv is pinned to an exact commit of an unmerged fork** fixing
  `play_url` on tvOS 26 ([PR #2846](https://github.com/postlund/pyatv/pull/2846)).
  Once merged and released, the pin in `scripts/atv.py` can go back to
  stock `pyatv`.
- **Netflix deep links are unreliable** since its Sept 2025 tvOS app
  update; the skill falls back to launch-and-type.
- JustWatch lookups default to US/en; override with `ATV_JW_COUNTRY` /
  `ATV_JW_LANGUAGE`.
- YouTube and `play` playback use AirPlay 2: queued on the TV, continues
  after the command exits; stream URLs expire after ~6h. Some sites
  (e.g. Vimeo) block yt-dlp extraction with a 403 — AirPlay from a
  phone/browser is the fallback there.
- tvOS may show an "Open in YouTube" confirmation for `--app` opens —
  a human must accept it with the physical remote.
- Tested on tvOS 26 (Apple TV 4K gen 3). tvOS 13+ should work.

## License

MIT
