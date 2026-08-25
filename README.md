<p align="center">
  <img src="assets/logo.svg" width="128" alt="appletv-remote logo"/>
</p>

<h1 align="center">appletv-remote</h1>

<p align="center">
  <strong>The complete Claude Code / opencode skill for agentic Apple TV control.</strong><br/>
  "Watch Severance." "Put the new Veritasium video on." "Pause, volume 30." — your agent just does it.
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"/>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab"/>
  <img alt="tvOS 26 tested" src="https://img.shields.io/badge/tvOS-26%20tested-000000"/>
  <img alt="No server" src="https://img.shields.io/badge/server-none-5e5ce6"/>
</p>

---

No remote. No Siri. No server, no daemon — every action is a one-shot
local command over Apple's own protocols, powered by
[pyatv](https://github.com/postlund/pyatv). Prefer an MCP server
instead? That's the sibling project:
[appletv-mcp](https://github.com/slandau3/appletv-mcp) — same
capabilities, same pairing, MCP form.

## Why this one

Other Apple TV integrations stop at "press a button." This one finds
content and plays it:

| | appletv-remote | mcp-pyatv | Home Assistant |
|---|---|---|---|
| "Watch \<title\>" by name (JustWatch → deep link) | ✅ | ❌ | manual URLs |
| Play **any** video URL / ~1,800 sites (yt-dlp → AirPlay) | ✅ | ❌ | ❌ |
| YouTube by search terms | ✅ | ❌ | ❌ |
| Deep links into titles (Apple TV+, Disney+, Max, Hulu, …) | ✅ | ❌ | manual |
| Absolute volume 0–100, seek, repeat, shuffle | ✅ | ❌ | partial |
| AirPlay audio output routing (HomePods) | ✅ | ❌ | ❌ |
| Multi-TV with self-healing IPs | ✅ | ❌ | partial |
| tvOS 26 AirPlay video push that actually works | ✅ | ❌ | ❌ |
| Zero infrastructure (no MCP server, no HA instance) | ✅ | ✅ | ❌ |

## Install

**Prerequisite:** [uv](https://docs.astral.sh/uv/) (`brew install uv`).
Everything else — Python, pyatv, yt-dlp — resolves automatically from
the script's inline dependencies.

```bash
git clone https://github.com/slandau3/appletv-remote.git
cp -r appletv-remote ~/.claude/skills/appletv-remote   # Claude Code + opencode
uv run ~/.claude/skills/appletv-remote/scripts/atv.py pair   # one-time, PIN on TV
```

Pairing stores credentials owner-only (0600) in
`~/.config/appletv-remote/devices.json`. Keep that file private — it
grants full control of the TV, and it's not part of this repo. Restart
your agent; it picks up the skill automatically.

## Commands (what the agent runs)

```
atv.py watch "severance" [--service "disney+"]   # find + pull up a title
atv.py youtube "veritasium" [--app]              # play YouTube (or in-app)
atv.py play <url>                                # ANY video URL / ~1800 sites
atv.py open <deep-link-url>                      # route any URL to its app
atv.py launch netflix                            # open an app (or bundle id)
atv.py remote <action>                           # 26 buttons: navigate, media,
                                                 #   control_center, screensaver…
atv.py volume [0-100|up|down]                    # get / step / absolute volume
atv.py seek <seconds>                            # seek in current media
atv.py repeat <off|track|all>                    # repeat mode
atv.py shuffle <off|songs|albums>                # shuffle mode
atv.py outputs [set <name>]                      # AirPlay audio outputs (HomePods)
atv.py type "text" [--clear]                     # type into the focused field
atv.py playing                                   # what's on + frontmost app
atv.py power wake|sleep                          # HDMI-CEC power
atv.py apps | devices | scan | use <name> | pair [name]
```

Global flags like `--device <name>` go **before** the subcommand.

## How it works

pyatv speaks Apple's **Companion** protocol (remote, apps, keyboard,
deep links) and **AirPlay 2** (video push, volume, output routing) on
your local network — no cloud, no account. Each command connects, acts,
and disconnects (~3–8s). If the TV's IP changes, the next command
re-finds it by its stable identifier and rewrites the config.

## Notes

- **pyatv is pinned to an exact commit of an unmerged fork** fixing
  `play_url` on tvOS 26 ([PR #2846](https://github.com/postlund/pyatv/pull/2846)).
  Once merged and released, the pin in `scripts/atv.py` can go back to
  stock `pyatv`.
- **Netflix deep links are unreliable** since its Sept 2025 tvOS app
  update; the skill falls back to launch-and-type.
- Some sites (e.g. Vimeo) bot-block yt-dlp extraction with a 403 —
  AirPlay from a phone/browser is the fallback.
- JustWatch lookups default to US/en; override with `ATV_JW_COUNTRY` /
  `ATV_JW_LANGUAGE`.
- Streamed URLs are IP-bound and expire (~6h) — always resolve fresh.
- Tested on tvOS 26 (Apple TV 4K gen 3). tvOS 13+ should work.

## Contributing

Issues and PRs welcome. The whole skill is one readable script
(`scripts/atv.py`, ~750 lines) plus `SKILL.md`.

## License

MIT — see [LICENSE](LICENSE).
