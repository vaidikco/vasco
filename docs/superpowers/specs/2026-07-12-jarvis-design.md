# Vasco AI Assistant - System Design

## Overview
A high-end, integrated desktop AI assistant for Windows, designed for an immersive, "Vasco-like" experience. The system is built incrementally, focusing on a fluid UI and an asynchronous core.

## Phase 1: Enhanced UI Shell (The Dynamic Island)
### Goal
Create a visually stunning, "Liquid Glass" UI shell that feels organic and integrated into the Windows desktop.

### Design Specifications
- **Motion**: Implement "Spring" physics for all transitions. Use an overshoot easing curve to simulate elasticity.
- **Visuals (Liquid Glass)**:
    - **Native Blur**: Use Win32 API (`SetWindowCompositionAttribute`) to enable the Acrylic blur-behind effect.
    - **Glassmorphism**: 
        - Semi-transparent background (`rgba(255, 255, 255, 0.1)`).
        - 1px bright border for edge definition.
        - Subtle radial gradient for a 3D curved effect.
    - **Frameless**: Always-on-top, translucent, tool-window style.

## Phase 2: Core Orchestration
### Goal
A non-blocking "Brain" that coordinates ASR, LLM, and TTS.

### Architecture
- **VascoCore**: Central controller utilizing an `asyncio` event loop.
- **State Machine**: Manages global states (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `EXECUTING`).
- **Event Bridge**: Uses PyQt signals to decouple the Core logic from the UI Shell.

## Phase 3: Intelligence & Actions
### Goal
Give Vasco "brains" and the ability to interact with the OS.

### Components
- **LLM Integration**: API-based (e.g., Claude 3.5 Sonnet or GPT-4o) with a tailored "Vasco" personality.
- **Action Registry**: A modular system of Python functions for OS control (e.g., `open_app`, `volume_control`, `web_search`).
- **Context Memory**: Short-term conversation history to maintain continuity.

## Success Criteria
- UI feels "liquid" and high-end.
- No UI freezing during LLM processing or TTS generation.
- Wake-word detection triggers a seamless transition to the "Listening" state.

