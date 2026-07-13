"""Router: action-first routing and graceful degradation without any LLM."""

import asyncio

import pytest

from vasco.router import BrainRouter


@pytest.fixture
def offline_router(monkeypatch):
    """A router with no Ollama and no Anthropic credentials."""
    router = BrainRouter()

    async def no_ollama(ttl=60.0):
        return False

    monkeypatch.setattr(router.ollama, "is_available", no_ollama)
    monkeypatch.setattr(router.claude, "credentials_available", lambda: False)
    return router


def test_action_route_needs_no_llm(offline_router):
    route, reply = asyncio.run(offline_router.respond("what time is it", []))
    assert route == "action"
    assert ":" in reply


def test_no_brain_degrades_gracefully(offline_router):
    route, reply = asyncio.run(offline_router.respond("tell me a joke", []))
    assert route == "none"
    assert "Anthropic" in reply or "Ollama" in reply


def test_cloud_route_selected_when_credentialed(monkeypatch):
    router = BrainRouter()
    monkeypatch.setattr(router.claude, "credentials_available", lambda: True)

    async def fake_claude(history, text):
        return "Certainly."

    monkeypatch.setattr(router.claude, "respond", fake_claude)
    route, reply = asyncio.run(router.respond("write me a poem", []))
    assert route == "cloud" and reply == "Certainly."


def test_local_route_when_only_ollama(monkeypatch):
    router = BrainRouter()
    monkeypatch.setattr(router.claude, "credentials_available", lambda: False)

    async def yes_ollama(ttl=60.0):
        return True

    async def fake_chat(messages, system=""):
        return "Local hello."

    monkeypatch.setattr(router.ollama, "is_available", yes_ollama)
    monkeypatch.setattr(router.ollama, "chat", fake_chat)
    route, reply = asyncio.run(router.respond("hello there", []))
    assert route == "local" and reply == "Local hello."
