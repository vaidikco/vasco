# Liquid Glass UI Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Dynamic Island UI shell with elastic transitions and native Windows Acrylic blur.

**Architecture:** Enhance the existing `DynamicIsland` class by integrating Win32 API hooks for background blur and replacing linear easing with a spring-like overshoot curve (`OutBack`).

**Tech Stack:** PyQt6, `ctypes` (Win32 API).

## Global Constraints
- Platform: Windows 10/11 (required for Acrylic blur).
- Window: Frameless, Always-on-top, Translucent.
- States: IDLE, LISTENING, THINKING, SPEAKING, EXECUTING.

---

### Task 1: Windows Acrylic Blur Integration

**Files:**
- Modify: `E:\ai\ui_shell.py`

**Interfaces:**
- Produces: `enable_blur_behind(self)` method that applies the native Windows blur effect to the current window.

- [ ] **Step 1: Implement Win32 API boilerplate**
  Add `ctypes` imports and define the necessary structures for the Acrylic effect: `ACCENT_POLICY`, `WINDOWCOMPOSITIONCORE`, and the `SetWindowCompositionAttribute` function signature.

- [ ] **Step 2: Create `enable_blur_behind` method**
  Implement the logic to call `SetWindowCompositionAttribute` using the window's handle (`self.winId()`).

- [ ] **Step 3: Integrate into `__init__`**
  Call `self.enable_blur_behind()` after setting window flags.

- [ ] **Step 4: Run and verify**
  Run `python E:\ai\ui_shell.py` and verify that the island background blurs the desktop content.

- [ ] **Step 5: Commit**
  `git add E:\ai\ui_shell.py`
  `git commit -m "feat(ui): add native Windows Acrylic blur effect"`

---

### Task 2: Glassmorphism Styling

**Files:**
- Modify: `E:\ai\ui_shell.py`

**Interfaces:**
- Modifies: `_get_style(self, color)` to return a glass-themed stylesheet.

- [ ] **Step 1: Update `_get_style` for glass effect**
  Change the style to use a semi-transparent white background, a thin bright border, and a subtle linear gradient to simulate glass.

- [ ] **Step 2: Update state colors to be semi-transparent**
  Update `self.states` to use `rgba` colors instead of hex codes to allow the blur and gradient to shine through.

- [ ] **Step 3: Run and verify**
  Verify the "liquid glass" look: check for the semi-transparency and the highlighted edges.

- [ ] **Step 4: Commit**
  `git add E:\ai\ui_shell.py`
  `git commit -m "feat(ui): implement glassmorphism aesthetics"`

---

### Task 3: Elastic Motion Implementation

**Files:**
- Modify: `E:\ai\ui_shell.py`

**Interfaces:**
- Modifies: `set_state` and animation setup.

- [ ] **Step 1: Change Easing Curve to `OutBack`**
  Replace `QEasingCurve.Type.InOutQuad` with `QEasingCurve.Type.OutBack` to create the elastic overshoot effect.

- [ ] **Step 2: Adjust Animation Duration**
  Increase duration from `300ms` to `450ms` to make the bounce more noticeable and organic.

- [ ] **Step 3: Run and verify**
  Trigger state changes and verify that the island "snaps" and slightly over-expands before settling.

- [ ] ** Step 4: Commit**
  `git add E:\ai\ui_shell.py`
  `git commit -m "feat(ui): add elastic spring animations"`
