"""
Conversation Manager — Handles continuous conversation mode.

Solves Problem 2: Users shouldn't have to say "Jarvis" before every command.
After wake-word activation, the assistant stays in conversation mode for
CONVERSATION_TIMEOUT seconds (default 120s / 2 minutes) of silence before returning to idle.

Thread-safe: can be called from the voice listener thread and the API thread.
"""

from __future__ import annotations

import threading
import time
import logging
from typing import Callable

from core.constants import CONVERSATION_TIMEOUT, AssistantState

log = logging.getLogger("services.conversation")


class ConversationManager:
    """
    Manages the assistant's active/idle lifecycle.

    States:
        IDLE         → listening for wake word only
        CONVERSATION → actively listening for commands (15s timeout)
        THINKING     → LLM is processing (no timeout reset)
        SPEAKING     → TTS is playing response

    After CONVERSATION_TIMEOUT seconds of no interaction,
    automatically returns to IDLE and calls the on_deactivate callback.
    """

    def __init__(
        self,
        timeout: float = CONVERSATION_TIMEOUT,
        on_deactivate: Callable[[], None] | None = None,
    ):
        self._timeout = timeout
        self._on_deactivate = on_deactivate
        self._state = AssistantState.IDLE
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._last_interaction: float = 0.0

    @property
    def state(self) -> AssistantState:
        return self._state

    @property
    def is_active(self) -> bool:
        """True if the assistant is in any non-idle state."""
        return self._state != AssistantState.IDLE

    def activate(self):
        """
        Enter conversation mode. Call when wake word is detected.
        If already active, this is a no-op (prevents duplicate activations).
        """
        with self._lock:
            if self._state != AssistantState.IDLE:
                log.debug("Already active — ignoring duplicate activation.")
                return
            self._state = AssistantState.CONVERSATION
            self._last_interaction = time.time()
            self._reset_timer()
            log.info("Conversation mode ACTIVATED.")

    def on_interaction(self):
        """
        Call whenever the user says something or sends a message.
        Resets the inactivity timer.
        """
        with self._lock:
            self._last_interaction = time.time()
            if self._state in (AssistantState.IDLE,):
                self._state = AssistantState.CONVERSATION
            self._reset_timer()

    def set_state(self, state: AssistantState):
        """Explicitly set the state (e.g., THINKING, SPEAKING)."""
        with self._lock:
            self._state = state
            # Pause timer completely while THINKING, SPEAKING, or EXECUTING — user shouldn't be timed out!
            if state in (AssistantState.THINKING, AssistantState.SPEAKING, AssistantState.EXECUTING):
                self._cancel_timer()
            elif state in (AssistantState.CONVERSATION, AssistantState.LISTENING):
                self._reset_timer()

    def deactivate(self):
        """Manually return to idle."""
        with self._lock:
            self._cancel_timer()
            self._state = AssistantState.IDLE
            log.info("Conversation mode DEACTIVATED (manual).")

    def _reset_timer(self):
        """Reset the inactivity timer. Must be called with lock held."""
        self._cancel_timer()
        self._timer = threading.Timer(self._timeout, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self):
        """Called when conversation times out. Returns to idle."""
        with self._lock:
            # DO NOT timeout if currently thinking, speaking, or executing!
            if self._state in (AssistantState.THINKING, AssistantState.SPEAKING, AssistantState.EXECUTING):
                log.debug("Currently active/thinking — postponing inactivity timeout.")
                self._reset_timer()
                return

            # Only timeout if we're in CONVERSATION state
            if self._state not in (AssistantState.CONVERSATION, AssistantState.LISTENING):
                self._reset_timer()
                return

            self._state = AssistantState.IDLE
            log.info(f"Conversation timed out after {self._timeout}s of silence.")

        # Notify the caller (e.g., to play a "going to sleep" sound)
        if self._on_deactivate:
            try:
                self._on_deactivate()
            except Exception as e:
                log.error(f"on_deactivate callback failed: {e}")

    def get_acknowledgment(self) -> str:
        """
        Get a contextual acknowledgment when the user says the wake word
        while already in conversation mode.
        """
        import random
        responses = [
            "Yes?",
            "I'm listening.",
            "What can I do?",
            "Go ahead.",
            "I'm here.",
        ]
        return random.choice(responses)
