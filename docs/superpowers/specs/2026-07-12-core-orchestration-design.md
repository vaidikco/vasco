# Vasco Core Orchestration Design

## Overview
The Core Orchestration layer is the "Brain" of the Vasco AI assistant. It coordinates the sensing (ASR), reasoning (LLM), and acting (Dynamic Execution) modules, while ensuring the UI (Dynamic Island) reflects the system state in real-time.

## Architecture
The system utilizes an asynchronous event-driven architecture powered by `asyncio` and `PyQt6` signals.

### 1. The Orchestration Loop (VascoCore)
The `VascoCore` class acts as the central hub. It manages a state machine and coordinates the data flow between modules.

**State Machine:**
- `IDLE`: Awaiting wake word.
- `LISTENING`: Capturing user voice command.
- `THINKING`: Processing intent via LLM.
- `SPEAKING`: Delivering audio response via TTS.
- `EXECUTING`: Running a dynamically generated script to perform an OS action.

### 2. The Hybrid Brain & Router
To balance performance, privacy, and intelligence, Vasco uses a hybrid routing system.

**Routing Logic:**
- **Local Model (Llama 3/Ollama)**: Handles `SYSTEM_ACTION` intents (e.g., "Open Notepad", "Mute Volume").
- **Cloud Model (Claude 3.5/GPT-4o)**: Handles `COMPLEX_QUERY` intents (e.g., "Write a poem", "Summarize this file").
- **Router**: A lightweight classification step that determines the destination based on a set of keywords and intent patterns.

### 3. The Dynamic Execution Engine
Instead of a fixed tool-set, Vasco employs a dynamic scripting engine for OS interaction.

**Execution Lifecycle:**
1. **Generation**: The LLM generates a Python script utilizing `pyautogui`, `pygetwindow`, and `subprocess`.
2. **Safety Filter**: A static analysis pass checks for forbidden commands (e.g., `rm -rf`, unauthorized registry edits).
3. **Execution**: The script is executed in a controlled environment.
4. **Observation**: Stdout and stderr are captured and fed back to the LLM if a self-correction loop is needed.

### 4. UI Synchronization
The `VascoCore` communicates with the `DynamicIsland` shell via `PyQt6` signals.

- **`state_changed(str)`**: Updates the island's visual state and triggers elastic animations.
- **`text_update(str)`**: Updates the island's label with real-time processing info.

## Success Criteria
- Zero UI freezing during LLM or script execution.
- Seamless transition from wake-word detection to action execution.
- Correct routing between local and cloud models.
- Safe execution of dynamically generated scripts.

