# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyatv @ git+https://github.com/jlacivita/pyatv@8848ad3fd9ae46b8eb733bfc667b536a28f04c5a",
#   "httpx>=0.27",
#   "yt-dlp>=2024.1.1",
#   "curl-cffi>=0.7",
# ]
# ///
# NOTE: pinned to an exact commit of an unmerged fork because upstream
# pyatv's play_url is broken on tvOS 26 (issues #2821/#2774, fix PR
# #2846). Once the PR merges and ships, switch back to "pyatv>=0.19" —
# everything else works with stock pyatv.
"""atv.py — control an Apple TV over the local network.

One-shot CLI: connects, performs a single action, disconnects.
Paired credentials live in ~/.config/appletv-remote/devices.json
(created by `atv.py pair`).

Usage:
  atv.py scan                          List Apple TVs found on the network
  atv.py pair [name]                   Pair a new TV (PIN appears on screen)
  atv.py devices                       List paired TVs and which is default
  atv.py use <name>                    Set the default TV
  atv.py remote <action>               up/down/left/right/select/menu/home/
                                       top_menu/home_hold/control_center/
                                       guide/screensaver/play/pause/
                                       play_pause/stop/next/previous/
                                       skip_forward/skip_backward/
                                       channel_up/channel_down/
                                       volume_up/volume_down/suspend/wakeup
  atv.py volume [0-100|up|down]        Get or set volume
  atv.py seek <seconds>                Seek to a position in current media
  atv.py repeat <off|track|all>        Set repeat mode
  atv.py shuffle <off|songs|albums>    Set shuffle mode
  atv.py outputs [set <name>]          List/set AirPlay audio outputs
  atv.py launch <app>                  Friendly name or bundle id
  atv.py open <url>                    Open a deep link (see SKILL.md catalog)
  atv.py watch <title> [--service S]   Find via JustWatch and pull it up
  atv.py youtube <url|id|search terms> Play a YouTube video
  atv.py play <url>                    Play any video URL: direct media
                                       files (.mp4/.m3u8/...) or any site
                                       yt-dlp supports (~1800). No DRM.
  atv.py type <text>                   Type into the focused on-screen field
  atv.py playing                       What's playing now
  atv.py power <wake|sleep>            Power via HDMI-CEC
  atv.py apps                          List installed apps

Global option: --device <name> to target a non-default TV.
Pairing for agents: set ATV_PIN_FILE=/tmp/atv_pin.txt and the pair
command reads each PIN from that file instead of prompting.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from pyatv import pair as atv_pair
from pyatv import scan as atv_scan
from pyatv import connect as atv_connect
from pyatv.const import Protocol, RepeatState, ShuffleState

CONFIG_DIR = Path.home() / ".config" / "appletv-remote"
CONFIG_PATH = CONFIG_DIR / "devices.json"

APP_ALIASES = {
    "tv": "com.apple.TVWatchList",
    "apple tv": "com.apple.TVWatchList",
    "netflix": "com.netflix.Netflix",
    "youtube": "com.google.ios.youtube",
    "disney+": "com.disney.disneyplus",
    "disney": "com.disney.disneyplus",
    "max": "com.wbd.stream",
    "hbo": "com.wbd.stream",
    "hbo max": "com.wbd.stream",
    "hulu": "com.hulu.plus",
    "prime": "com.amazon.aiv.AIVApp",
    "prime video": "com.amazon.aiv.AIVApp",
    "amazon": "com.amazon.aiv.AIVApp",
    "peacock": "com.peacocktv.peacock",
    "paramount+": "com.cbsvideo.app",
    "paramount": "com.cbsvideo.app",
    "plex": "com.plexapp.plex",
    "spotify": "com.spotify.client",
    "music": "com.apple.TVMusic",
    "podcasts": "com.apple.podcasts",
    "photos": "com.apple.TVPhotos",
    "settings": "com.apple.TVSettings",
    "app store": "com.apple.TVAppStore",
    "arcade": "com.apple.Arcade",
    "fitness": "com.apple.Fitness",
    "facetime": "com.apple.facetime",
    "search": "com.apple.TVSearch",
}

REMOTE_ACTIONS = [
    "up", "down", "left", "right", "select", "menu", "home",
    "top_menu", "home_hold", "control_center", "guide", "screensaver",
    "play", "pause", "play_pause", "stop", "next", "previous",
    "skip_forward", "skip_backward", "channel_up", "channel_down",
    "volume_up", "volume_down", "suspend", "wakeup",
]

REPEAT_MODES = {
    "off": RepeatState.Off,
    "track": RepeatState.Track,
    "all": RepeatState.All,
}
SHUFFLE_MODES = {
    "off": ShuffleState.Off,
    "songs": ShuffleState.Songs,
    "albums": ShuffleState.Albums,
}

JUSTWATCH_GRAPHQL = "https://apis.justwatch.com/graphql"

# Vendors without a tvOS app to deep-link into (physical media etc.).
PROVIDER_BLOCKLIST = {
    "amazon dvd / blu-ray",
    "zavvi",
    "barnes & noble",
    "fye",
    "target",
    "walmart",
}


# ---------------------------------------------------------------- config

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"default": None, "devices": {}}
    try:
        config = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        sys.exit(
            f"Config at {CONFIG_PATH} is corrupt ({e}). "
            "Delete it and re-run: atv.py pair"
        )
    if not isinstance(config, dict):
        sys.exit(
            f"Config at {CONFIG_PATH} has an unexpected shape. "
            "Delete it and re-run: atv.py pair"
        )
    config.setdefault("default", None)
    config.setdefault("devices", {})
    return config


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    os.chmod(CONFIG_PATH, 0o600)  # credentials — owner read/write only


def get_device(config: dict, name: str | None) -> tuple[str, dict]:
    devices = config.get("devices", {})
    if not devices:
        sys.exit(
            "No paired TVs. Run: atv.py pair  (see SKILL.md for details)"
        )
    chosen = name or config.get("default")
    if chosen is None:
        sys.exit(
            "No default TV set. Run: atv.py use <name>\n"
            f"Paired: {', '.join(devices)}"
        )
    if chosen not in devices:
        sys.exit(f"Unknown TV '{chosen}'. Paired: {', '.join(devices)}")
    device = dict(devices[chosen])
    device["_name"] = chosen
    return chosen, device


# ------------------------------------------------------------ connection

async def find_conf(device: dict):
    """Locate the TV by IP, falling back to its stable identifier.

    Self-heals the stored address after a DHCP lease change."""
    loop = asyncio.get_running_loop()
    devices = await atv_scan(loop, timeout=5.0)
    conf = next(
        (c for c in devices if str(c.address) == device["address"]), None
    )
    if conf is None and device.get("identifier"):
        conf = next(
            (c for c in devices if c.identifier == device["identifier"]),
            None,
        )
        if conf is not None:
            print(
                f"Note: TV moved to {conf.address} (was {device['address']}); "
                "updating config"
            )
            config = load_config()
            entry = config["devices"].get(device.get("_name"))
            if entry is not None:
                entry["address"] = str(conf.address)
                save_config(config)
    if conf is None:
        sys.exit(
            f"Apple TV at {device['address']} not found on the network. "
            "Is it awake and on the same network? Try: atv.py scan"
        )
    return conf


async def connect(device: dict):
    conf = await find_conf(device)
    companion = conf.get_service(Protocol.Companion)
    if companion is not None:
        companion.credentials = device["credentials"].get("companion")
    airplay = conf.get_service(Protocol.AirPlay)
    if airplay is not None:
        airplay.credentials = device["credentials"].get("airplay")
    return await atv_connect(conf, asyncio.get_running_loop())


# ----------------------------------------------------------------- pair

async def wait_for_pin_file(pin_file: str, protocol_name: str) -> str:
    print(
        f"[{protocol_name}] PIN shown on TV. Waiting for it in {pin_file} ...",
        flush=True,
    )
    for _ in range(600):
        if os.path.exists(pin_file):
            pin = Path(pin_file).read_text().strip()
            os.remove(pin_file)
            if pin:
                return pin
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for PIN in {pin_file}")


async def cmd_pair(args) -> None:
    loop = asyncio.get_running_loop()
    found = await atv_scan(loop, timeout=5.0)
    tvs = [c for c in found if c.device_info.model is not None]
    if not tvs:
        sys.exit("No devices found. Is the Apple TV on this network?")

    print("Devices on the network:")
    for i, c in enumerate(tvs):
        print(f"  [{i}] {c.name} — {c.device_info.model} at {c.address}")

    target = None
    pin_file = os.environ.get("ATV_PIN_FILE")
    if args.name:
        target = next(
            (c for c in tvs if c.name and args.name.lower() in c.name.lower()),
            None,
        )
        if target is None:
            sys.exit(f"No device matching '{args.name}' in the list above.")
    elif len(tvs) == 1:
        target = tvs[0]
    elif pin_file:
        sys.exit(
            "Multiple devices found; in ATV_PIN_FILE mode you must pass a "
            "name filter: atv.py pair <name>"
        )
    else:
        choice = input("Number to pair: ").strip()
        try:
            target = tvs[int(choice)]
        except (ValueError, IndexError):
            sys.exit(f"'{choice}' is not a valid choice.")

    print(f"Pairing with {target.name} at {target.address} ...")
    credentials = {}

    for protocol in (Protocol.Companion, Protocol.AirPlay):
        if target.get_service(protocol) is None:
            continue
        pairing = await atv_pair(target, protocol, loop)
        try:
            await pairing.begin()
            if pin_file:
                pin = await wait_for_pin_file(pin_file, protocol.name)
            else:
                pin = input(f"[{protocol.name}] PIN shown on TV: ").strip()
            if not pin.isdigit():
                sys.exit(f"Invalid PIN '{pin}' — expected digits.")
            pairing.pin(int(pin))
            await pairing.finish()
        finally:
            await pairing.close()
        if not pairing.has_paired:
            sys.exit(f"[{protocol.name}] Pairing failed — try again.")
        credentials[protocol.name.lower()] = pairing.service.credentials
        print(f"[{protocol.name}] paired.")

    config = load_config()
    name = target.name or f"tv-{len(config['devices']) + 1}"
    if name in config["devices"]:
        print(f"Note: re-pairing existing TV '{name}', updating credentials")
    identifier = target.identifier or str(target.address)
    config["devices"][name] = {
        "address": str(target.address),
        "identifier": identifier,
        "credentials": credentials,
    }
    if not config.get("default"):
        config["default"] = name
    save_config(config)
    print(f"Saved '{name}' to {CONFIG_PATH} (default: {config['default']})")


# ------------------------------------------------------------- commands

async def cmd_scan(_args) -> None:
    loop = asyncio.get_running_loop()
    found = await atv_scan(loop, timeout=5.0)
    for c in found:
        model = c.device_info.model or "unknown"
        print(f"{c.name} — {model} at {c.address} (id: {c.identifier})")


async def cmd_devices(_args) -> None:
    config = load_config()
    if not config["devices"]:
        print("No paired TVs.")
        return
    for name, d in config["devices"].items():
        marker = " (default)" if name == config.get("default") else ""
        print(f"{name}{marker} — {d['address']}")


async def cmd_use(args) -> None:
    config = load_config()
    if args.name not in config["devices"]:
        sys.exit(f"Unknown TV '{args.name}'. Paired: {', '.join(config['devices'])}")
    config["default"] = args.name
    save_config(config)
    print(f"Default TV is now '{args.name}'")


async def cmd_remote(args, device) -> None:
    action = args.action.lower().strip()
    if action not in REMOTE_ACTIONS:
        sys.exit(f"Unknown action '{action}'. Valid: {', '.join(REMOTE_ACTIONS)}")
    atv = await connect(device)
    try:
        await getattr(atv.remote_control, action)()
        print(f"Pressed {action}")
    finally:
        atv.close()


async def cmd_launch(args, device) -> None:
    bundle_id = APP_ALIASES.get(args.app.lower().strip(), args.app)
    atv = await connect(device)
    try:
        await atv.apps.launch_app(bundle_id)
        print(f"Launched {args.app} ({bundle_id})")
    finally:
        atv.close()


async def cmd_open(args, device) -> None:
    atv = await connect(device)
    try:
        await atv.apps.launch_app(args.url)
        print(f"Opened {args.url}")
    finally:
        atv.close()


async def cmd_apps(_args, device) -> None:
    atv = await connect(device)
    try:
        for app in await atv.apps.app_list():
            print(f"{app.name} — {app.identifier}")
    finally:
        atv.close()


async def cmd_playing(_args, device) -> None:
    atv = await connect(device)
    try:
        p = await atv.metadata.playing()
        app = None
        try:
            app = atv.metadata.app
        except Exception:
            pass
        print(
            f"state={p.device_state} title={p.title} artist={p.artist} "
            f"album={p.album} app={app} position={p.position}/{p.total_time}s"
        )
    finally:
        atv.close()


async def cmd_volume(args, device) -> None:
    atv = await connect(device)
    try:
        level = args.level
        if level is None or level == "get":
            print(f"volume={atv.audio.volume:.0f}")
        elif level == "up":
            await atv.audio.volume_up()
            print(f"volume={atv.audio.volume:.0f}")
        elif level == "down":
            await atv.audio.volume_down()
            print(f"volume={atv.audio.volume:.0f}")
        else:
            await atv.audio.set_volume(float(level))
            print(f"volume set to {level}")
    finally:
        atv.close()


async def cmd_seek(args, device) -> None:
    atv = await connect(device)
    try:
        await atv.remote_control.set_position(int(args.seconds))
        print(f"Seeked to {args.seconds}s")
    finally:
        atv.close()


async def cmd_repeat(args, device) -> None:
    atv = await connect(device)
    try:
        await atv.remote_control.set_repeat(REPEAT_MODES[args.mode])
        print(f"Repeat: {args.mode}")
    finally:
        atv.close()


async def cmd_shuffle(args, device) -> None:
    atv = await connect(device)
    try:
        await atv.remote_control.set_shuffle(SHUFFLE_MODES[args.mode])
        print(f"Shuffle: {args.mode}")
    finally:
        atv.close()


async def cmd_outputs(args, device) -> None:
    atv = await connect(device)
    try:
        if args.action == "set":
            if not args.name:
                sys.exit("Usage: atv.py outputs set <name>")
            devices = atv.audio.output_devices
            match = next(
                (d for d in devices if args.name.lower() in d.name.lower()),
                None,
            )
            if match is None:
                names = ", ".join(d.name for d in devices) or "none"
                sys.exit(f"No output matching '{args.name}'. Available: {names}")
            await atv.audio.set_output_devices([match.identifier])
            print(f"Audio output set to {match.name}")
        else:
            for d in atv.audio.output_devices:
                print(f"{d.name} — {d.identifier}")
    finally:
        atv.close()


async def cmd_type(args, device) -> None:
    atv = await connect(device)
    try:
        if args.clear:
            await atv.keyboard.text_clear()
        await atv.keyboard.text_append(args.text)
        print(f"Typed: {args.text}")
    finally:
        atv.close()


async def cmd_power(args, device) -> None:
    atv = await connect(device)
    try:
        if args.action == "sleep":
            await atv.power.turn_off()
            print("Apple TV put to sleep")
        else:
            await atv.power.turn_on()
            print("Apple TV woken")
    finally:
        atv.close()


def _pick_stream(entry: dict, fallback_title: str) -> tuple[str, str]:
    """Pick (title, stream_url) from a yt-dlp info entry.

    Prefers the HLS master manifest: the Apple TV's native player
    handles adaptive variants and separate audio renditions itself.
    Falls back to the best progressive format (video+audio in one file).
    """
    formats = entry.get("formats", [])
    hls = next((f for f in formats if f.get("manifest_url")), None)
    if hls is not None:
        return entry.get("title", fallback_title), hls["manifest_url"]
    progressive = [
        f for f in formats
        if f.get("vcodec", "none") != "none"
        and f.get("acodec", "none") != "none"
        and f.get("url")
    ]
    if progressive:
        best = max(progressive, key=lambda f: f.get("height") or 0)
        return entry.get("title", fallback_title), best["url"]
    # Some extractors put a direct URL on the entry without formats.
    if entry.get("url") and not formats:
        return entry.get("title", fallback_title), entry["url"]
    raise RuntimeError(
        "No playable stream found (unsupported or DRM-protected page)"
    )


def _page_resolve(url: str) -> tuple[str, str]:
    """Resolve any video page URL to (title, stream_url).

    Direct media files skip extraction; everything else goes through
    yt-dlp, which supports ~1800 sites. DRM services (Netflix etc.)
    cannot be extracted — use `watch`/`open` deep links for those."""
    if re.search(r"\.(mp4|m3u8|mov|m4v|webm)(\?|#|$)", url, re.I):
        return url, url
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        entry = (info.get("entries") or [info])[0]
        return _pick_stream(entry, url)


async def _play_stream(device: dict, title: str, stream_url: str) -> None:
    """Queue a stream on the TV via AirPlay and confirm it started.

    play_url blocks monitoring playback until the media ends — run it
    as a task, give the TV a few seconds to start, then return.
    Playback is queued on the TV itself and survives the CLI exiting."""
    atv = await connect(device)
    try:
        play_task = asyncio.ensure_future(atv.stream.play_url(stream_url))

        def _log_late_failure(task: asyncio.Task) -> None:
            if not task.cancelled() and task.exception() is not None:
                print(
                    f"Playback ended with error: {task.exception()}",
                    file=sys.stderr,
                )

        play_task.add_done_callback(_log_late_failure)
        await asyncio.sleep(8)
        if play_task.done() and play_task.exception() is not None:
            sys.exit(1)  # the callback already printed the error
        print(f"Playing: {title}")
    finally:
        atv.close()


async def cmd_play(args, device) -> None:
    try:
        title, stream_url = await asyncio.get_running_loop(
        ).run_in_executor(None, _page_resolve, args.url)
    except Exception as e:
        sys.exit(f"Error resolving video: {type(e).__name__}: {e}")
    if title != args.url:
        print(f"Found: {title}")
    await _play_stream(device, title, stream_url)


async def cmd_youtube(args, device) -> None:
    query = args.query.strip()
    video_id = None

    match = re.search(
        r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([\w-]{11})", query
    )
    if match:
        video_id = match.group(1)
    elif re.fullmatch(r"[\w-]{11}", query):
        video_id = query  # probable bare ID; falls back to search on failure

    import yt_dlp

    def _resolve(vid: str | None, terms: str):
        """Return (video_id, title, stream_url) for an id or search terms."""
        opts = {"quiet": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            target = f"ytsearch1:{terms}" if vid is None else (
                f"https://www.youtube.com/watch?v={vid}"
            )
            try:
                info = ydl.extract_info(target, download=False)
            except Exception:
                if vid is None or vid != terms:
                    raise
                # An 11-char search term misread as a bare video ID.
                info = ydl.extract_info(f"ytsearch1:{terms}", download=False)
            entry = (info.get("entries") or [info])[0]
            title, stream_url = _pick_stream(entry, "?")
            return entry["id"], title, stream_url

    vid, title, stream_url = await asyncio.get_running_loop().run_in_executor(
        None, _resolve, video_id, query
    )
    print(f"Found: {title} ({vid})")

    if args.app:
        # Open inside the YouTube app instead of the system player.
        # tvOS may show an "Open in YouTube" confirmation that a human
        # must accept with the physical remote — never blind-press
        # select to confirm it.
        url = f"youtube://www.youtube.com/watch?v={vid}"
        atv = await connect(device)
        try:
            await atv.apps.launch_app(url)
        finally:
            atv.close()
        print(f"Opened in YouTube app: {url}")
        print(
            "(If a confirmation dialog appears, a human must accept it "
            "with the physical remote.)"
        )
    else:
        await _play_stream(device, title, stream_url)


async def _justwatch_search(query: str) -> list[dict] | None:
    """Unofficial JustWatch GraphQL search → [{provider, url}].

    Subscription streaming offers first, purchase/rental after, physical
    media removed, one offer per provider. Offers are merged across the
    top few title matches, so ambiguous queries can surface the wrong
    title's links — callers print what they're opening. Region comes
    from ATV_JW_COUNTRY/ATV_JW_LANGUAGE (default US/en). Returns None on
    transport/API failure, [] when the title simply has no offers."""
    import httpx

    gql = """
    query SearchTitles($searchTitlesFilter: TitleFilter!, $country: Country!,
                       $language: Language!, $first: Int!) {
      popularTitles(country: $country, filter: $searchTitlesFilter,
                    first: $first, sortBy: POPULAR) {
        edges {
          node {
            ... on MovieOrShow {
              content(country: $country, language: $language) { title }
              offers(country: $country, platform: WEB) {
                monetizationType
                package { clearName }
                standardWebURL
              }
            }
          }
        }
      }
    }
    """
    payload = {
        "query": gql,
        "variables": {
            "searchTitlesFilter": {"searchQuery": query},
            "country": os.environ.get("ATV_JW_COUNTRY", "US"),
            "language": os.environ.get("ATV_JW_LANGUAGE", "en"),
            "first": 3,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(JUSTWATCH_GRAPHQL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        edges = data.get("data", {}).get("popularTitles", {}).get("edges", [])
        streaming, purchase, seen = [], [], set()
        for edge in edges:
            for offer in edge.get("node", {}).get("offers", []) or []:
                url = offer.get("standardWebURL")
                provider = offer.get("package", {}).get("clearName", "?")
                key = provider.lower()
                if not url or key in seen or key in PROVIDER_BLOCKLIST:
                    continue
                seen.add(key)
                entry = {"provider": provider, "url": url}
                if offer.get("monetizationType") in ("FLATRATE", "ADS", "FREE"):
                    streaming.append(entry)
                else:
                    purchase.append(entry)
        return streaming + purchase
    except Exception:
        return None


async def cmd_watch(args, device) -> None:
    offers = await _justwatch_search(args.title)
    if offers is None:
        sys.exit(
            "JustWatch lookup failed (network or API change). "
            "Fallback: launch the app and use `type` to search inside it, "
            "or find a URL and use `open`."
        )
    if not offers:
        sys.exit(
            f"No streaming deep link found for '{args.title}'. "
            "Fallback: launch the app and use `type` to search inside it, "
            "or find a URL and use `open`."
        )

    if args.service:
        wanted = args.service.lower().strip()
        chosen = next(
            (o for o in offers if wanted in o["provider"].lower()), None
        )
        if chosen is None:
            available = ", ".join(o["provider"] for o in offers)
            sys.exit(
                f"'{args.title}' not found on {args.service}. "
                f"Available on: {available}"
            )
    else:
        chosen = offers[0]

    atv = await connect(device)
    try:
        await atv.apps.launch_app(chosen["url"])
        print(f"Pulling up '{args.title}' via {chosen['provider']}")
        print(f"URL: {chosen['url']}")
    finally:
        atv.close()


# ------------------------------------------------------------------ cli

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="Paired TV name (default: configured)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="List Apple TVs on the network")
    sub.add_parser("devices", help="List paired TVs")

    p = sub.add_parser("pair", help="Pair a new TV (PIN on screen)")
    p.add_argument("name", nargs="?", help="Name filter from scan results")

    p = sub.add_parser("use", help="Set the default TV")
    p.add_argument("name")

    p = sub.add_parser("remote", help="Press a remote button")
    p.add_argument("action")

    p = sub.add_parser("launch", help="Launch an app")
    p.add_argument("app")

    p = sub.add_parser("open", help="Open a deep link URL")
    p.add_argument("url")

    sub.add_parser("apps", help="List installed apps")
    sub.add_parser("playing", help="What's playing")

    p = sub.add_parser("type", help="Type into the focused field")
    p.add_argument("text")
    p.add_argument(
        "--clear",
        action="store_true",
        help="Clear the field before typing",
    )

    p = sub.add_parser("volume", help="Get or set volume")
    p.add_argument(
        "level",
        nargs="?",
        help="0-100, 'up', 'down', or omit to read current volume",
    )

    p = sub.add_parser("seek", help="Seek to a position in current media")
    p.add_argument("seconds", type=int)

    p = sub.add_parser("repeat", help="Set repeat mode")
    p.add_argument("mode", choices=list(REPEAT_MODES))

    p = sub.add_parser("shuffle", help="Set shuffle mode")
    p.add_argument("mode", choices=list(SHUFFLE_MODES))

    p = sub.add_parser("outputs", help="List or set AirPlay audio outputs")
    p.add_argument("action", nargs="?", default="list", choices=["list", "set"])
    p.add_argument("name", nargs="?", help="Output name when action=set")

    p = sub.add_parser("power", help="Power control")
    p.add_argument("action", choices=["wake", "sleep"])

    p = sub.add_parser("youtube", help="Play a YouTube video")
    p.add_argument("query", help="URL, video id, or search terms")
    p.add_argument(
        "--app",
        action="store_true",
        help="Open in the YouTube app instead of the system player "
        "(tvOS may show a confirmation dialog a human must accept)",
    )

    p = sub.add_parser("play", help="Play any video URL on the TV")
    p.add_argument(
        "url",
        help="Direct media URL (.mp4/.m3u8/...) or a video page from any "
        "site yt-dlp supports. DRM services are not supported.",
    )

    p = sub.add_parser("watch", help="Find a title and pull it up")
    p.add_argument("title")
    p.add_argument("--service", help="e.g. 'netflix', 'disney+', 'apple tv'")

    return parser


async def dispatch(args) -> None:
    handlers = {
        "scan": cmd_scan,
        "devices": cmd_devices,
        "use": cmd_use,
        "pair": cmd_pair,
    }
    if args.command in handlers:
        await handlers[args.command](args)
        return

    config = load_config()
    _name, device = get_device(config, args.device)
    device_handlers = {
        "remote": cmd_remote,
        "launch": cmd_launch,
        "open": cmd_open,
        "apps": cmd_apps,
        "playing": cmd_playing,
        "type": cmd_type,
        "power": cmd_power,
        "youtube": cmd_youtube,
        "play": cmd_play,
        "watch": cmd_watch,
        "volume": cmd_volume,
        "seek": cmd_seek,
        "repeat": cmd_repeat,
        "shuffle": cmd_shuffle,
        "outputs": cmd_outputs,
    }
    await device_handlers[args.command](args, device)


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        # Agent-facing CLI: a clean one-line error beats a traceback.
        sys.exit(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
