"""Vasco's hybrid brain: built-in actions, local LLM (Ollama), optional cloud (Claude).

Routing order for a command:
1. ActionRegistry regex match -> run the action instantly, no LLM at all.
2. Otherwise the FREE local brain (Ollama, e.g. llama3) answers — no API key,
   no per-request cost, no rate limit that runs out.
3. Only if the user has explicitly configured Anthropic credentials does the
   optional cloud brain (Claude, with tool use) take over as an upgrade.
4. If neither a local nor a cloud brain is reachable, a canned reply explains
   how to bring the free local brain online.

Design note: Vasco defaults to local so it stays private, offline-capable,
and never depends on a paid or metered API.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

from vasco.actions import ActionRegistry, registry as default_registry
from vasco.config import config
from vasco import platform_utils as plat

logger = logging.getLogger("BrainRouter")

VASCO_PERSONA = f"""You are Vasco, a JARVIS-inspired desktop AI assistant running locally on the user's {plat.PLATFORM_NAME} machine.

Personality: capable, warm, lightly witty — a trusted aide, never sycophantic.

Your replies are spoken aloud by text-to-speech, so:
- Keep responses to one to three short sentences unless the user asks for detail.
- Never use markdown, bullet lists, code blocks, or emoji — plain spoken prose only.
- Numbers and abbreviations should be written the way they are spoken.

You can control the computer through the tools provided. Use them whenever the
user asks you to act (open things, search, check the time, adjust volume,
take screenshots). Chain several tools for compound requests. After acting,
confirm briefly what you did. If the user references earlier conversation,
respect it. If context labeled "Relevant Memories" or "Screen Content" is
attached to a message, treat it as trusted background information."""


class OllamaClient:
    """Async wrapper for a local Ollama server, with cached availability probe."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or config.ollama_url).rstrip("/")
        self.model = model or config.ollama_model
        self._available: Optional[bool] = None
        self._checked_at = 0.0

    async def is_available(self, ttl: float = 60.0) -> bool:
        now = time.monotonic()
        if self._available is not None and now - self._checked_at < ttl:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                self._available = resp.status_code == 200
        except Exception:
            self._available = False
        self._checked_at = now
        if not self._available:
            logger.info("Ollama not reachable at %s", self.base_url)
        return self._available

    async def chat(self, messages: List[Dict], system: str = "") -> str:
        payload_messages = (
            [{"role": "system", "content": system}] if system else []
        ) + messages
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": payload_messages, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()


class ClaudeClient:
    """Optional cloud brain: Claude with the action registry exposed as tools.

    Never used unless the user has explicitly set Anthropic credentials, so the
    default experience stays entirely on the free local model.
    """

    def __init__(self, actions: ActionRegistry):
        self.actions = actions
        self._client = None

    @staticmethod
    def credentials_available() -> bool:
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return True
        # `ant auth login` profiles are picked up automatically by the SDK.
        profile_dir = Path.home() / ".config" / "anthropic"
        return profile_dir.exists() and any(profile_dir.glob("credentials/*.json"))

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic()
        return self._client

    async def respond(self, history: List[Dict], user_text: str) -> str:
        """Run the agentic loop: Claude may call OS-action tools before replying."""
        import anthropic

        client = self._get_client()
        messages = list(history) + [{"role": "user", "content": user_text}]
        tools = self.actions.to_anthropic_tools()

        try:
            for _ in range(8):  # cap tool-use iterations
                response = await client.messages.create(
                    model=config.anthropic_model,
                    max_tokens=config.max_tokens,
                    system=VASCO_PERSONA,
                    output_config={"effort": config.effort},
                    tools=tools,
                    messages=messages,
                )

                if response.stop_reason == "refusal":
                    return "I'm sorry, I can't help with that request."

                if response.stop_reason == "pause_turn":
                    messages.append({"role": "assistant", "content": response.content})
                    continue

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    tool_results = []
                    for block in response.content:
                        if block.type != "tool_use":
                            continue
                        logger.info("Tool call: %s(%s)", block.name, block.input)
                        loop = asyncio.get_running_loop()
                        result = await loop.run_in_executor(
                            None, self.actions.execute, block.name, dict(block.input)
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )
                    messages.append({"role": "user", "content": tool_results})
                    continue

                text = "".join(b.text for b in response.content if b.type == "text").strip()
                return text or "Done."

            return "I got stuck in a loop trying to do that, so I stopped."

        except anthropic.AuthenticationError:
            return "My optional cloud brain isn't authenticated, so I'll stick to the local model."
        except anthropic.RateLimitError:
            return "The cloud brain is rate limited right now. Give me a moment and try again."
        except anthropic.APIConnectionError:
            return "I can't reach the internet right now, so the cloud brain is offline."
        except anthropic.APIStatusError as e:
            logger.error("Claude API error %s: %s", e.status_code, e.message)
            return "Something went wrong talking to the cloud brain."


class BrainRouter:
    """Decides who answers: a built-in action, the free local model, or optional cloud."""

    def __init__(self, actions: ActionRegistry | None = None):
        self.actions = actions or default_registry
        self.ollama = OllamaClient()
        self.claude = ClaudeClient(self.actions)

    async def respond(self, text: str, history: List[Dict]) -> Tuple[str, str]:
        """Returns (route, spoken_reply)."""
        # 1. Direct action match — instant and offline.
        match = self.actions.match_text(text)
        if match:
            action, kwargs = match
            loop = asyncio.get_running_loop()
            reply = await loop.run_in_executor(
                None, self.actions.execute, action.name, kwargs
            )
            return "action", reply

        # 2. Optional cloud brain — ONLY if the user configured Anthropic creds.
        if self.claude.credentials_available():
            reply = await self.claude.respond(history, text)
            return "cloud", reply

        # 3. Free local brain (default). No API key, no cost, no rate cap.
        if await self.ollama.is_available():
            try:
                messages = list(history) + [{"role": "user", "content": text}]
                reply = await self.ollama.chat(messages, system=VASCO_PERSONA)
                return "local", reply or "I'm not sure what to say to that."
            except Exception as e:
                logger.error("Ollama request failed: %s", e)

        # 4. Nothing available — tell the user how to bring the free brain online.
        return "none", (
            "My local brain isn't running. Start Ollama with 'ollama serve' and "
            "pull a model like llama3, and I'll be able to think for you — no API key needed."
        )
