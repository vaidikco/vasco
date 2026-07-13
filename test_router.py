import asyncio
import logging
from unittest.mock import AsyncMock, patch
from Vasco_core import VascoCore, VascoState

# Mock for VascoSignals since we are in a headless test environment
class MockSignals:
    def __init__(self):
        self.state_changed = self.MockSignal()

    class MockSignal:
        def emit(self, value):
            print(f" [Signal] state_changed -> {value}")

async def main():
    logging.basicConfig(level=logging.INFO)
    signals = MockSignals()
    core = VascoCore(signals)

    test_cases = [
        ("Open Notepad", "local", "local"),
        ("Write a poem about quantum physics", "cloud", "cloud"),
    ]

    for text, expected_route, mock_response in test_cases:
        print(f"\nTesting: '{text}' (Expected route: {expected_route})")

        # Mock the local client's generate method to simulate the classifier's response
        with patch.object(core.router.local_client, 'generate', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_response

            route = await core.process_text(text)
            print(f"Result: {route}")
            assert route == expected_route, f"Expected {expected_route}, but got {route}"

    print("\nAll routing tests passed!")

if __name__ == "__main__":
    asyncio.run(main())


