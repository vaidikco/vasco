import logging
import httpx
import os
from typing import Tuple
from anthropic import Anthropic

logger = logging.getLogger("BrainRouter")

class LocalLLMClient:
    """Wrapper for Ollama (local LLM)."""
    def __init__(self, model: str = "llama3"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    async def generate(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    json={"model": self.model, "prompt": prompt, "stream": False},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"LocalLLMClient error: {e}")
            return "Error: Local LLM unavailable."

class CloudLLMClient:
    """Wrapper for Cloud LLM (Anthropic Claude)."""
    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    async def generate(self, prompt: str) -> str:
        try:
            # Note: anthropic SDK is sync by default, using to_thread for async wrapper
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                    model="claude-3-sonnet-20240229"
                )
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"CloudLLMClient error: {e}")
            return "Error: Cloud LLM unavailable."

class BrainRouter:
    """Routes user intent to either Local or Cloud LLM."""
    def __init__(self):
        self.local_client = LocalLLMClient()
        self.cloud_client = CloudLLMClient()

    async def route_intent(self, text: str) -> Tuple[str, str]:
        """
        Classifies intent using the local LLM.
        Returns ('local', prompt) or ('cloud', prompt).
        """
        classification_prompt = (
            f"Classify the following user request as either 'local' (simple system commands, "
            f"app launches, or basic tasks) or 'cloud' (complex reasoning, creative writing, "
            f"deep knowledge, or coding). Respond with ONLY the word 'local' or 'cloud'.\n\n"
            f"Request: {text}\n"
            f"Classification:"
        )

        decision = await self.local_client.generate(classification_prompt)
        decision = decision.lower().strip()

        if "cloud" in decision:
            return "cloud", text
        return "local", text

    async def process(self, text: str) -> str:
        """High-level entry point to route and get a response."""
        route, prompt = await self.route_intent(text)
        logger.info(f"Routing request to {route}: {text}")

        if route == "cloud":
            return await self.cloud_client.generate(prompt)
        return await self.local_client.generate(prompt)

