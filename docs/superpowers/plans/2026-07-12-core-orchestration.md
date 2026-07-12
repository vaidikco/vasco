# Core Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the central "Brain" that coordinates ASR, LLM, and TTS while updating the Dynamic Island UI.

**Architecture:** An asynchronous orchestrator (`JarvisCore`) that manages a state machine and routes intents between local/cloud LLMs and a dynamic OS execution engine.

**Tech Stack:** Python 3.11+, `asyncio`, `PyQt6`, `ollama` (Local LLM), `openai/anthropic` (Cloud LLM).

## Global Constraints
- Platform: Windows 10/11.
- Window: Frameless, Always-on-top, Translucent.
- States: IDLE, LISTENING, THINKING, SPEAKING, EXECUTING.
- UI Responsiveness: Zero freezing during async operations.

---

### Task 1: The Async Signal Bridge & State Machine

**Files:**
- Create: `E:\ai\core_bridge.py`
- Modify: `E:\ai\ui_shell.py`

**Interfaces:**
- Produces: `JarvisSignals(QObject)` with signals `state_changed(str)` and `text_update(str)`.

- [ ] **Step 1: Create `core_bridge.py` with `JarvisSignals` class**
  Define a `QObject` that contains the signals used to sync the Core and the UI.

- [ ] **Step 2: Integrate `JarvisSignals` into `DynamicIsland`**
  Modify `ui_shell.py` to accept a `JarvisSignals` instance and connect its signals to `set_state` and a new `update_text` method.

- [ ] **Step 3: Verify signal connectivity**
  Write a test script that emits a signal and verify the Dynamic Island changes state visually.

- [ ] **Step 4: Commit**
  `git add E:\ai\core_bridge.py E:\ai\ui_shell.py`
  `git commit -m "feat(core): implement PyQt signal bridge for state sync"`

---

### Task 2: JarvisCore & Asyncio Orchestrator

**Files:**
- Create: `E:\ai\jarvis_core.py`
- Modify: `E:\ai\ui_shell.py` (entry point)

**Interfaces:**
- Consumes: `JarvisSignals`
- Produces: `JarvisCore.run()` async entry point.

- [ ] **Step 1: Implement `JarvisCore` state management**
  Create the core class with an internal state machine and the `asyncio` event loop.

- [ ] **Step 2: Implement the Async Loop Worker**
  Create a `QThread` wrapper that runs the `asyncio` loop, allowing `JarvisCore` to run in the background without blocking the UI.

- [ ] **Step 3: Verify loop execution**
  Run a test where `JarvisCore` emits a "THINKING" signal every 2 seconds to the UI.

- [ ] **Step 4: Commit**
  `git add E:\ai\jarvis_core.py E:\ai\ui_shell.py`
  `git commit -m "feat(core): implement asyncio orchestrator and thread worker"`

---

### Task 3: Hybrid Router & LLM Integration

**Files:**
- Create: `E:\ai\brain_router.py`
- Modify: `E:\ai\jarvis_core.py`

**Interfaces:**
- Consumes: User text input.
- Produces: `route_intent(text) -> ("local" | "cloud", prompt)`.

- [ ] **Step 1: Implement Local LLM Client (Ollama)**
  Create a wrapper for Ollama to handle simple system intent classification.

- [ ] **Step 2: Implement Cloud LLM Client (API)**
  Create a wrapper for the Cloud LLM (Claude/GPT) for complex reasoning.

- [ ] **Step 3: Implement Routing Logic**
  Create the `BrainRouter` that classifies intents and directs them to the appropriate model.

- [ ] **Step 4: Verify routing**
  Test with "Open Notepad" (Local) and "Explain quantum physics" (Cloud) and verify the destination.

- [ ] **Step 5: Commit**
  `git add E:\ai\brain_router.py E:\ai\jarvis_core.py`
  `git commit -m "feat(brain): implement hybrid local/cloud routing"`

---

### Task 4: Dynamic Execution Engine (The Agent)

**Files:**
- Create: `E:\ai\executor.py`
- Modify: `E:\ai\jarvis_core.py`

**Interfaces:**
- Consumes: LLM-generated Python code.
- Produces: `execute_script(code) -> (success, output)`.

- [ ] **Step 1: Implement the Safety Filter**
  Create a validator that scans code for forbidden keywords (`os.remove`, `shutil`, etc.).

- [ ] **Step 2: Implement the Script Runner**
  Create a method that executes the validated code using `exec()` and captures stdout/stderr.

- [ ] **Step 3: Integrate with Core state**
  Ensure the core transitions to `EXECUTING` during script runs.

- [ ] **Step 4: Verify a system action**
  Test: LLM generates a script to open a specific app $\rightarrow$ Core executes $\rightarrow$ App opens.

- [ ] **Step 5: Commit**
  `git add E:\ai\executor.py E:\ai\jarvis_core.py`
  `git commit -m "feat(executor): implement dynamic script execution and safety filter"`

---

### Task 5: Full Pipeline Integration (ASR -> LLM -> TTS)

**Files:**
- Modify: `E:\ai\jarvis_core.py`
- Modify: `E:\ai\asr_module.py`
- Modify: `E:\ai\tts_module.py`
- Modify: `E:\ai\ui_shell.py` (Main entry)

**Interfaces:**
- End-to-End Flow: Wake Word $\rightarrow$ Listen $\rightarrow$ Route $\rightarrow$ Execute/Reason $\rightarrow$ Speak.

- [ ] **Step 1: Connect ASR callback to `JarvisCore`**
  Modify `SpeechRecognizer` to emit a signal/event that the Core catches to start the `LISTENING` state.

- [ ] **Step 2: Connect Core to TTS**
  Integrate `TextToSpeech.speak()` into the final stage of the Core's pipeline.

- [ ] **Step 3: Final End-to-End Test**
  Test the full flow: "Hey Jarvis" $\rightarrow$ "Open Chrome" $\rightarrow$ (Island animates) $\rightarrow$ Chrome opens $\rightarrow$ "Opening Chrome now".

- [ ] **Step 4: Commit**
  `git add .`
  `git commit -m "feat(core): full end-to-end integration of ASR, Brain, and TTS"`
