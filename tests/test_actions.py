"""Action registry: pattern matching, schemas, and safe handlers."""

import re

from vasco import actions
from vasco.actions import ActionRegistry

registry = ActionRegistry()


def match_name(text):
    m = registry.match_text(text)
    return m[0].name if m else None


def test_time_and_date():
    assert match_name("what time is it") == "current_time"
    assert match_name("what's the time") == "current_time"
    assert match_name("what day is it") == "current_date"


def test_screenshot_not_hijacked_by_ocr_or_apps():
    assert match_name("take a screenshot") == "take_screenshot"


def test_volume_extracts_level():
    action, kwargs = registry.match_text("set volume to 40")
    assert action.name == "set_volume" and kwargs == {"level": 40}


def test_mute_and_unmute():
    action, kwargs = registry.match_text("mute")
    assert action.name == "mute" and kwargs == {"muted": True}
    action, kwargs = registry.match_text("unmute")
    assert action.name == "mute" and kwargs == {"muted": False}


def test_web_search_extracts_query():
    action, kwargs = registry.match_text("search for cats wearing hats")
    assert action.name == "web_search" and kwargs["query"] == "cats wearing hats"


def test_open_url_vs_open_app():
    action, kwargs = registry.match_text("open github.com")
    assert action.name == "open_url" and kwargs["url"] == "github.com"
    action, kwargs = registry.match_text("open safari")
    assert action.name == "open_app" and kwargs["app_name"] == "safari"


def test_named_sites_and_explicit_browser_requests_use_browser_action():
    action, kwargs = registry.match_text("open youtube")
    assert action.name == "open_website" and kwargs == {"destination": "youtube"}
    action, kwargs = registry.match_text("open a pasta recipe in browser")
    assert action.name == "open_website"
    assert kwargs == {"destination": "a pasta recipe"}


def test_named_site_opens_a_new_browser_tab(monkeypatch):
    opened = []
    monkeypatch.setattr(actions.plat, "IS_MACOS", False)
    monkeypatch.setattr(actions.webbrowser, "open_new_tab", opened.append)
    reply = actions.open_website("YouTube")
    assert opened == ["https://www.youtube.com"]
    assert "Opening YouTube" in reply


def test_weather_matches_with_and_without_location():
    action, kwargs = registry.match_text("what is the weather in tokyo")
    assert action.name == "get_weather" and kwargs["location"] == "tokyo"
    action, kwargs = registry.match_text("weather")
    assert action.name == "get_weather" and kwargs == {}
    assert match_name("temperature in London") == "get_weather"


def test_remembering_weather_is_not_a_weather_lookup():
    # "remember ..." is handled by the core before routing; the registry should
    # still not treat a storage sentence as a live weather request destination.
    action, kwargs = registry.match_text("what's the weather like in new york")
    assert action.name == "get_weather" and "new york" in kwargs["location"]


def test_compound_commands_defer_to_llm():
    assert registry.match_text("open safari and search for cats") is None


def test_chitchat_does_not_match():
    assert registry.match_text("why is the sky blue") is None
    assert registry.match_text("tell me a joke") is None


def test_time_handler_runs():
    action, kwargs = registry.match_text("what time is it")
    result = registry.execute(action.name, kwargs)
    assert re.search(r"\d{1,2}:\d{2}", result)


def test_anthropic_tool_schemas_valid():
    tools = registry.to_anthropic_tools()
    assert len(tools) >= 8
    for tool in tools:
        assert set(tool) == {"name", "description", "input_schema"}
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert isinstance(schema.get("required", []), list)


def test_unknown_action_is_graceful():
    assert "Unknown action" in registry.execute("self_destruct", {})
