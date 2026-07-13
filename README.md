# Vasco 🌌
**Your Local AI System Agent.**

Vasco is a high-end, Jarvis-style desktop assistant for Windows, designed to be more than just a chatbot. He is a **Full System Agent** capable of sensing your environment, remembering your preferences through a visual brain, and executing complex OS-level tasks.

---

## ✨ Key Features

### 🏝️ Dynamic Island UI
A fluid, glassmorphic interface that sits at the top of your screen.
- **Liquid Motion**: Smooth animations using elastic easing curves.
- **Acrylic Blur**: Native Windows 11 Acrylic effect for a seamless, modern look.
- **Adaptive States**: Transitions between `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `EXECUTING`, and `SCANNING`.

### 🧠 Visual Brain (Semantic Memory)
Vasco doesn't just store data; he maintains a knowledge graph.
- **Obsidian Integration**: Memories are stored as Markdown files in a vault, making them human-readable and editable.
- **Semantic Search**: Powered by `sentence-transformers`, allowing Vasco to recall contextually relevant facts instead of just keyword matches.

### ⚡ Full System Agency
Unlike typical AI, Vasco can actually *do* things on your computer.
- **Dynamic Execution**: Generates and executes Python scripts on-the-fly to control the OS.
- **AST Safety Guard**: Every generated script is passed through a strict Abstract Syntax Tree (AST) whitelist validator to ensure security and prevent malicious operations.

### 👂 Adaptive Sensing
- **Voice Calibration**: A first-run "voice test" that learns your specific pronunciation of "Hey Vasco".
- **Proactive Agency**: A background observer that monitors active windows and performs OCR scans to detect errors or crashes, offering help before you even ask.

---

## 🛠️ Technical Architecture

- **Language**: Python 3.10+
- **UI Framework**: PyQt6
- **Async Orchestration**: `asyncio` event loop running in a dedicated `QThread` for zero-lag UI.
- **Sensing**: `vosk` (ASR), `edge-tts` (TTS), `pygetwindow` & `easyocr` (Environment Sensing).
- **Intelligence**: Hybrid Routing between Local LLMs (Ollama) and Cloud LLMs (Claude/GPT).

---

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/vaidikco/vasco.git
cd vasco
```

### 2. Install Dependencies
```bash
pip install PyQt6 vosk sounddevice edge-tts pygetwindow easyocr sentence-transformers
```

### 3. Run Vasco
```bash
python ui_shell.py
```

*Note: On first run, Vasco will ask you to calibrate your wake word. Please follow the prompts in the Dynamic Island.*

---

## 🛡️ Privacy & Security
Vasco is designed to be local-first. 
- **Local Memory**: Your brain vault stays on your machine.
- **Secure Execution**: The `SafetyVisitor` ensures only approved Python modules and functions are executed.
- **Observer Toggle**: You can disable background sensing at any time by saying *"disable observer"*.

---

## 🤝 Credits
Developed by [Subham Choudhury](https://github.com/vaidikco)
