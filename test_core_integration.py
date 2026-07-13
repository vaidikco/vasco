import asyncio
import logging
from unittest.mock import MagicMock
from Vasco_core import VascoCore, VascoState

# Mock PyQt signals
class MockSignals:
    def __init__(self):
        self.state_changed = MagicMock()
        self.text_update = MagicMock()

async def test_open_notepad():
    logging.basicConfig(level=logging.INFO)
    signals = MockSignals()
    core = VascoCore(signals)

    print("\n--- Simulating Request: 'Open Notepad' ---")
    route = await core.process_text("Open Notepad")

    print(f"Router Result: {route}")

    # Verify state transitions (implicitly via logs or by checking mocks)
    # state_changed.emit was called with "THINKING", "EXECUTING", then "IDLE"
    calls = [call.args[0] for call in signals.state_changed.emit.call_args_list]
    print(f"State Transitions: {calls}")

    assert "EXECUTING" in calls, "Core should have entered EXECUTING state"
    assert calls[-1] == "IDLE", "Core should have returned to IDLE state"
    assert route == "local", "Router should have selected 'local'"

    print("\n--- Integration Test Passed! ---")

if __name__ == "__main__":
    asyncio.run(test_open_notepad())


