"""Core integration: wake flow, states, memory writes, history — all headless."""

import asyncio

import pytest

from vasco.core import VascoCore, VascoState
from vasco.memory import MemoryManager


class RecordingSignal:
    def __init__(self):
        self.values = []

    def emit(self, *args):
        self.values.append(args[0] if args else None)


class RecordingSignals:
    def __init__(self):
        self.state_changed = RecordingSignal()
        self.text_update = RecordingSignal()


class FakeRouter:
    """Stands in for BrainRouter — no network, deterministic replies."""

    def __init__(self):
        from vasco.actions import ActionRegistry
        self.actions = ActionRegistry()
        self.seen = []

    async def respond(self, text, history):
        self.seen.append((text, list(history)))
        match = self.actions.match_text(text)
        if match:
            return "action", "Action done."
        return "cloud", f"Echo: {text}"


@pytest.fixture
def core(tmp_path, monkeypatch):
    signals = RecordingSignals()
    memory = MemoryManager(vault_path=tmp_path / "vault")
    monkeypatch.setattr(memory, "_get_model", lambda: None)
    c = VascoCore(signals=signals, router=FakeRouter(), memory=memory)
    return c


def run(coro):
    return asyncio.run(coro)


async def _with_loop(core, coro_fn):
    core.loop = asyncio.get_running_loop()
    return await coro_fn()


def test_command_returns_reply_and_states(core):
    async def go():
        return await core.process_command("why is the sky blue")

    reply = run(_with_loop(core, go))
    assert reply == "Echo: why is the sky blue"
    states = core.signals.state_changed.values
    assert "THINKING" in states and "SPEAKING" in states
    assert states[-1] == "IDLE"


def test_action_command_uses_executing_state(core):
    async def go():
        return await core.process_command("what time is it")

    reply = run(_with_loop(core, go))
    assert reply == "Action done."
    assert "EXECUTING" in core.signals.state_changed.values


def test_wake_word_enters_listening(core):
    async def go():
        await core._process_asr_logic("hey vasco")
        return core.state

    state = run(_with_loop(core, go))
    assert state == VascoState.LISTENING


def test_wake_word_with_embedded_command(core):
    async def go():
        await core._process_asr_logic("hey vasco what time is it")
        return core.state

    state = run(_with_loop(core, go))
    assert state == VascoState.IDLE  # command processed, back to idle
    assert any("time" in t for t, _ in core.router.seen)


def test_non_wake_speech_ignored_when_idle(core):
    async def go():
        await core._process_asr_logic("the weather is nice today")
        return core.state

    state = run(_with_loop(core, go))
    assert state == VascoState.IDLE
    assert core.router.seen == []


def test_remember_that_capitalized_no_crash(core):
    """The old code crashed with IndexError on 'Remember that ...'."""
    async def go():
        return await core.process_command("Remember that my car is a blue honda")

    reply = run(_with_loop(core, go))
    assert "memory" in reply.lower()
    notes = list(core.memory.vault_path.rglob("*.md"))
    assert notes and "blue honda" in notes[0].read_text()


def test_memories_injected_into_context(core):
    async def go():
        await core.process_command("remember that my dog is called biscuit")
        await core.process_command("what is my dog called biscuit")
        return core.router.seen

    seen = run(_with_loop(core, go))
    assert any("Relevant Memories" in text for text, _ in seen)


def test_history_alternates_and_trims(core):
    async def go():
        for i in range(12):
            await core.process_command(f"question number {i}")
        return core.history

    history = run(_with_loop(core, go))
    assert len(history) <= 12
    assert history[0]["role"] == "user"
    roles = [m["role"] for m in history]
    assert roles == ["user", "assistant"] * (len(history) // 2)


def test_memory_answers_when_no_llm(tmp_path, monkeypatch):
    """With no LLM at all, a matching memory is still a useful answer."""
    class NoBrainRouter(FakeRouter):
        async def respond(self, text, history):
            self.seen.append((text, list(history)))
            return "none", "I don't have a language model available."

    memory = MemoryManager(vault_path=tmp_path / "vault")
    monkeypatch.setattr(memory, "_get_model", lambda: None)
    c = VascoCore(signals=RecordingSignals(), router=NoBrainRouter(), memory=memory)

    async def go():
        c.loop = asyncio.get_running_loop()
        await c.process_command("remember that the garage code is four two seven one")
        return await c.process_command("what is the garage code")

    reply = run(go())
    assert "four two seven one" in reply


def test_continuous_mode_relistens_after_reply(tmp_path, monkeypatch):
    """With conversation mode on and a mic present, Vasco keeps listening."""
    class FakeASR:
        def __init__(self): self.command_mode = False
        def pause(self): pass
        def resume(self): pass
        def set_command_mode(self, on): self.command_mode = on

    memory = MemoryManager(vault_path=tmp_path / "vault")
    monkeypatch.setattr(memory, "_get_model", lambda: None)
    c = VascoCore(signals=RecordingSignals(), router=FakeRouter(),
                  memory=memory, asr=FakeASR())
    c.set_continuous(True)

    async def go():
        c.loop = asyncio.get_running_loop()
        await c.process_command("why is the sky blue")
        return c.state

    assert run(go()) == VascoState.LISTENING  # stayed listening, not IDLE


def test_default_returns_to_idle_after_reply(core):
    async def go():
        return await core.process_command("why is the sky blue")

    run(_with_loop(core, go))
    assert core.state == VascoState.IDLE  # conversation mode off by default


def test_listen_timeout_returns_to_idle(core, monkeypatch):
    from vasco import core as core_mod
    monkeypatch.setattr(core_mod.config, "listen_timeout", 0.05)

    async def go():
        core.loop = asyncio.get_running_loop()
        core._enter_listening()
        assert core.state == VascoState.LISTENING
        await asyncio.sleep(0.15)
        return core.state

    assert run(go()) == VascoState.IDLE
