"""Vasco's hands: a registry of built-in, cross-platform OS actions.

Each action is exposed two ways:
1. Regex patterns — instant, offline matching for direct commands
   ("open safari", "what time is it") with no LLM round-trip at all.
2. Anthropic tool schemas — the cloud brain can call the same actions as
   tools ("find me a pasta recipe" -> web_search(...)).

This replaces the old approach of asking an LLM to generate arbitrary
Python for OS control: a fixed, audited action set is faster, works
offline, and is far safer. The script sandbox remains available for
computations, not for OS access.
"""

import datetime as _dt
import logging
import re
import subprocess
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, quote_plus

from vasco import platform_utils as plat
from vasco.config import config

logger = logging.getLogger("Actions")

# Friendly names -> per-OS application names
_APP_ALIASES = {
    "darwin": {
        "notepad": "TextEdit", "text editor": "TextEdit", "calculator": "Calculator",
        "browser": "Safari", "terminal": "Terminal", "music": "Music",
        "settings": "System Settings", "files": "Finder", "finder": "Finder",
    },
    "win32": {
        "notepad": "notepad", "text editor": "notepad", "calculator": "calc",
        "browser": "start msedge", "terminal": "cmd", "files": "explorer",
        "settings": "ms-settings:",
    },
    "linux": {
        "text editor": "gedit", "calculator": "gnome-calculator",
        "browser": "xdg-open https://", "files": "nautilus",
    },
}

# Names people naturally say out loud mapped to a useful starting page.  These
# are deliberately a small, transparent allow-list: unfamiliar destinations
# are searched for rather than guessed as URLs.
_BROWSER_SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "you tube": "https://www.youtube.com",
    "you-tube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "amazon": "https://www.amazon.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "whatsapp": "https://web.whatsapp.com",
    "linkedin": "https://www.linkedin.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
}


@dataclass
class Action:
    name: str
    description: str
    handler: Callable[..., str]
    patterns: List[re.Pattern] = field(default_factory=list)
    input_schema: Dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    )


# --------------------------------------------------------------------------
# Handlers (each returns a short sentence suitable for text-to-speech)
# --------------------------------------------------------------------------

def open_app(app_name: str) -> str:
    app_name = app_name.strip()
    platform_key = "darwin" if plat.IS_MACOS else "win32" if plat.IS_WINDOWS else "linux"
    resolved = _APP_ALIASES[platform_key].get(app_name.lower(), app_name)

    if plat.IS_MACOS:
        ok, out = plat.run(["open", "-a", resolved])
        return f"Opening {resolved}." if ok else f"I couldn't find an app called {app_name}."
    if plat.IS_WINDOWS:
        try:
            subprocess.Popen(f'start "" "{resolved}"', shell=True)
            return f"Opening {resolved}."
        except OSError:
            return f"I couldn't open {app_name}."
    exe = plat.which(resolved.split()[0])
    if exe:
        subprocess.Popen([exe])
        return f"Opening {resolved}."
    return f"I couldn't find {app_name} on this system."


def _open_in_default_browser(url: str) -> bool:
    """Open a URL through the OS default browser and report real success."""
    try:
        # On macOS this is more reliable than Python's browser registry and
        # respects the user's chosen default browser (Safari, Chrome, etc.).
        if plat.IS_MACOS:
            ok, _ = plat.run(["open", url])
            return ok
        # webbrowser.open_new_tab returns False on some platforms even when it
        # succeeds, so treat "no exception raised" as success.
        webbrowser.open_new_tab(url)
        return True
    except Exception as e:
        logger.warning("Could not open browser URL %s: %s", url, e)
        return False


def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if _open_in_default_browser(url):
        return f"Opening {url} in your default browser."
    return "I couldn't open your default browser."


def web_search(query: str) -> str:
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    if _open_in_default_browser(url):
        return f"Searching the web for {query}."
    return "I couldn't open your default browser to search the web."


def open_website(destination: str) -> str:
    """Open a named site, or search for a spoken destination in the browser."""
    destination = destination.strip(" .!?")
    key = destination.lower()
    url = _BROWSER_SITES.get(key)
    if url:
        if _open_in_default_browser(url):
            return f"Opening {destination} in your default browser."
        return "I couldn't open your default browser."
    url = f"https://www.google.com/search?q={quote_plus(destination)}"
    if _open_in_default_browser(url):
        return f"Searching your browser for {destination}."
    return "I couldn't open your default browser to search for that."


def get_weather(location: str = "") -> str:
    """Live weather via wttr.in (free, no API key). location='' uses your area."""
    import httpx

    location = (location or "").strip(" .?!")
    url = f"https://wttr.in/{quote(location)}?format=j1" if location else "https://wttr.in/?format=j1"
    try:
        resp = httpx.get(url, timeout=6.0, headers={"User-Agent": "curl/8"})
        resp.raise_for_status()
        data = resp.json()
        cur = data["current_condition"][0]
        desc = cur["weatherDesc"][0]["value"].lower()
        metric = config.weather_units.lower() != "imperial"
        temp = cur["temp_C"] if metric else cur["temp_F"]
        feels = cur["FeelsLikeC"] if metric else cur["FeelsLikeF"]
        unit = "degrees" if metric else "degrees Fahrenheit"
        if location:
            where = f" in {location.title()}"  # honor what the user asked for
        else:
            try:
                where = f" in {data['nearest_area'][0]['areaName'][0]['value']}"
            except (KeyError, IndexError):
                where = ""
        report = f"It's {temp} {unit} and {desc}{where}"
        if feels != temp:
            report += f", feels like {feels}"
        return re.sub(r"\s+", " ", report).strip() + "."
    except Exception as e:
        logger.warning("Weather lookup failed: %s", e)
        spot = f" for {location}" if location else ""
        return f"I couldn't get the weather{spot} right now."


def current_time() -> str:
    return "It's " + _dt.datetime.now().strftime("%I:%M %p").lstrip("0") + "."


def current_date() -> str:
    return "Today is " + _dt.datetime.now().strftime("%A, %B %d, %Y") + "."


def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    if plat.IS_MACOS:
        ok, _ = plat.run(["osascript", "-e", f"set volume output volume {level}"])
        return f"Volume set to {level} percent." if ok else "I couldn't change the volume."
    if plat.IS_LINUX and plat.which("amixer"):
        ok, _ = plat.run(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"])
        return f"Volume set to {level} percent." if ok else "I couldn't change the volume."
    return "Volume control isn't supported on this platform yet."


def mute(muted: bool = True) -> str:
    if plat.IS_MACOS:
        state = "true" if muted else "false"
        ok, _ = plat.run(["osascript", "-e", f"set volume output muted {state}"])
        if ok:
            return "Muted." if muted else "Unmuted."
    return "Mute isn't supported on this platform yet."


def take_screenshot() -> str:
    target = Path.home() / "Desktop"
    target = target if target.exists() else Path.home()
    out_file = target / f"vasco_screenshot_{_dt.datetime.now():%Y%m%d_%H%M%S}.png"
    if plat.IS_MACOS:
        ok, _ = plat.run(["screencapture", "-x", str(out_file)])
        return f"Screenshot saved to your desktop." if ok else "Screenshot failed."
    try:
        import mss
        with mss.mss() as sct:
            sct.shot(output=str(out_file))
        return "Screenshot saved to your desktop."
    except ImportError:
        return "I need the 'mss' package installed to take screenshots on this platform."
    except Exception as e:
        return f"Screenshot failed: {e}"


def system_info() -> str:
    import platform as py_platform
    parts = [f"You're on {plat.PLATFORM_NAME} ({py_platform.machine()})."]
    if plat.IS_MACOS:
        ok, out = plat.run(["pmset", "-g", "batt"])
        if ok:
            m = re.search(r"(\d+)%", out)
            if m:
                parts.append(f"Battery is at {m.group(1)} percent.")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def _p(*regexes: str) -> List[re.Pattern]:
    return [re.compile(r, re.IGNORECASE) for r in regexes]


class ActionRegistry:
    def __init__(self):
        self.actions: Dict[str, Action] = {}
        for a in self._defaults():
            self.actions[a.name] = a

    def _defaults(self) -> List[Action]:
        return [
            Action(
                "current_time", "Get the current local time.", current_time,
                _p(r"\bwhat(?:'s| is)? the time\b", r"\bwhat time is it\b", r"^time$"),
            ),
            Action(
                "current_date", "Get today's date.", current_date,
                _p(r"\bwhat(?:'s| is)? (?:the |today'?s )?date\b", r"\bwhat day is it\b"),
            ),
            Action(
                "get_weather",
                "Get the current weather. Optionally for a specific place.",
                get_weather,
                _p(r"\b(?:weather|temperature|forecast|how hot|how cold)\b"
                   r"(?:.*?\b(?:in|for|at|near)\s+(?P<location>[a-z .'-]+))?[?.!]*$"),
                {
                    "type": "object",
                    "properties": {"location": {"type": "string", "description": "City/place, optional"}},
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            Action(
                "take_screenshot", "Capture the screen to an image file on the desktop.",
                take_screenshot,
                _p(r"\btake a screenshot\b", r"\bscreenshot\b", r"\bcapture (?:the |my )?screen\b"),
            ),
            Action(
                "set_volume", "Set system output volume to a level from 0 to 100.",
                set_volume,
                _p(r"\b(?:set (?:the )?volume to|volume) (?P<level>\d{1,3})(?: percent)?\b"),
                {
                    "type": "object",
                    "properties": {"level": {"type": "integer", "description": "0-100"}},
                    "required": ["level"],
                    "additionalProperties": False,
                },
            ),
            Action(
                "mute", "Mute or unmute system audio.", mute,
                _p(r"^(?P<muted>mute)(?: the)?(?: audio| sound| volume)?$",
                   r"^(?:un[- ]?mute)(?: the)?(?: audio| sound| volume)?$"),
                {
                    "type": "object",
                    "properties": {"muted": {"type": "boolean"}},
                    "required": ["muted"],
                    "additionalProperties": False,
                },
            ),
            Action(
                "web_search", "Open a web search for a query in the default browser.",
                web_search,
                _p(r"\b(?:search(?: the web)?(?: for)?|google) (?P<query>.+)$"),
                {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            Action(
                "open_url", "Open a URL in the default browser.", open_url,
                _p(r"\b(?:open|go to) (?P<url>[\w.-]+\.[a-z]{2,}\S*)\b"),
                {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                    "additionalProperties": False,
                },
            ),
            Action(
                "open_website",
                "Open a well-known website in the default browser, or search for a destination.",
                open_website,
                _p(
                    r"^(?:open|visit|go to)(?: the)? (?P<destination>[\w .&'-]+?)(?: (?:in|on)(?: my| the)?(?: default)? browser)?[.!]?$"
                ),
                {
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "A site or thing to open in the browser.",
                        }
                    },
                    "required": ["destination"],
                    "additionalProperties": False,
                },
            ),
            Action(
                "open_app", "Open a desktop application by name.", open_app,
                _p(r"^(?:open|launch|start)(?: the)?(?: app(?:lication)?)? (?P<app_name>[\w .&-]+?)[.!]?$"),
                {
                    "type": "object",
                    "properties": {"app_name": {"type": "string"}},
                    "required": ["app_name"],
                    "additionalProperties": False,
                },
            ),
            Action(
                "system_info", "Report platform and battery status.", system_info,
                _p(r"\bbattery\b", r"\bsystem info(?:rmation)?\b"),
            ),
        ]

    def match_text(self, text: str) -> Optional[Tuple[Action, Dict]]:
        """Try to match a spoken command directly to an action (no LLM needed).

        Registration order matters: more specific actions (time, screenshot,
        search) are checked before the greedy open_app pattern.
        """
        text = text.strip()
        # Compound commands ("open safari and search for cats") need the
        # LLM to plan multiple tool calls — don't grab them with one regex.
        if re.search(r"\b(?:and then|and|then)\b", text) and len(text.split()) > 4:
            return None
        for action in self.actions.values():
            for pattern in action.patterns:
                m = pattern.search(text)
                if m:
                    kwargs = {k: v for k, v in m.groupdict().items() if v is not None}
                    # Keep normal desktop-app commands such as "open Safari"
                    # with open_app. This browser action claims named sites or
                    # an explicit "in browser" request only.
                    if action.name == "open_website":
                        destination = kwargs.get("destination", "").lower().strip()
                        explicitly_browser = bool(re.search(
                            r"\b(?:in|on)(?: (?:my|the))?(?: default)? browser\b", text,
                            re.IGNORECASE,
                        ))
                        if destination not in _BROWSER_SITES and not explicitly_browser:
                            continue
                    if action.name == "mute":
                        kwargs = {"muted": "muted" in kwargs}
                    if action.name == "set_volume" and "level" in kwargs:
                        kwargs["level"] = int(kwargs["level"])
                    return action, kwargs
        return None

    def execute(self, name: str, kwargs: Dict) -> str:
        action = self.actions.get(name)
        if not action:
            return f"Unknown action: {name}"
        try:
            return action.handler(**kwargs)
        except Exception as e:
            logger.exception("Action %s failed", name)
            return f"The action failed: {e}"

    def to_anthropic_tools(self) -> List[Dict]:
        """Expose every action as a Claude tool definition."""
        return [
            {
                "name": a.name,
                "description": a.description,
                "input_schema": a.input_schema,
            }
            for a in self.actions.values()
        ]

registry = ActionRegistry()
