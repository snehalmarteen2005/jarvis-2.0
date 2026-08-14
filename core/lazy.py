"""
Lazy initialization manager.

Defers ALL heavy imports and initialization (LangGraph, Ollama, SQLite)
until the first real user interaction. This makes startup < 2 seconds.

On an HDD, loading the Ollama model takes 3-8 seconds. By deferring it,
the user hears the wake-word acknowledgment instantly while the heavy
init happens in the background.
"""

from __future__ import annotations

import threading
import logging

log = logging.getLogger("core.lazy")


class LazyLoader:
    """
    Thread-safe lazy initializer for heavy components.

    Usage:
        LazyLoader.ensure_ready()     # blocks until all components loaded
        graph = LazyLoader.get_graph() # returns compiled LangGraph
    """

    _graph = None
    _checkpointer = None
    _llm = None
    _db_ready = False

    _initializing = False
    _init_lock = threading.Lock()
    _init_event = threading.Event()

    @classmethod
    def is_ready(cls) -> bool:
        return cls._init_event.is_set()

    @classmethod
    def ensure_ready(cls, timeout: float = 45.0) -> bool:
        """
        Ensure all heavy components are loaded.
        Returns True if ready, False if timed out.
        """
        if cls._init_event.is_set():
            return True

        with cls._init_lock:
            if cls._init_event.is_set():
                return True
            if cls._initializing:
                # Another thread is already doing the init — just wait
                return cls._init_event.wait(timeout=timeout)
            cls._initializing = True

        # Do the heavy init in a background thread
        t = threading.Thread(target=cls._init_heavy, daemon=True, name="lazy-init")
        t.start()
        return cls._init_event.wait(timeout=timeout)

    @classmethod
    def start_background_init(cls):
        """
        Non-blocking version: kicks off init in the background.
        Call this when the wake word is first detected.
        """
        if cls._init_event.is_set() or cls._initializing:
            return

        with cls._init_lock:
            if cls._initializing:
                return
            cls._initializing = True

        threading.Thread(target=cls._init_heavy, daemon=True, name="lazy-init").start()

    @classmethod
    def _init_heavy(cls):
        """
        The actual heavy initialization. Runs in a background thread.
        Order matters: DB first, then LLM, then graph.
        """
        try:
            log.info("Starting heavy initialization...")

            # 1. Database
            log.info("Initializing database...")
            from liebchen.database.models import initialize_database
            initialize_database()
            cls._db_ready = True
            log.info("Database ready.")

            # 2. LLM client
            log.info("Connecting to Ollama...")
            from liebchen.llm.ollama_client import get_llm
            cls._llm = get_llm()
            log.info("LLM client ready.")

            # 3. Agent graph
            log.info("Building agent graph...")
            from liebchen.agent.graph import build_graph
            cls._graph, cls._checkpointer = build_graph(llm=cls._llm)
            log.info("Agent graph compiled.")

            cls._init_event.set()
            log.info("Heavy initialization complete.")

        except Exception as e:
            log.error(f"Heavy initialization FAILED: {e}", exc_info=True)
            # Allow retry on next call
            cls._initializing = False

    @classmethod
    def get_graph(cls):
        """Get the compiled LangGraph. Blocks until ready."""
        cls.ensure_ready()
        return cls._graph

    @classmethod
    def get_llm(cls):
        """Get the Ollama LLM client. Blocks until ready."""
        cls.ensure_ready()
        return cls._llm

    @classmethod
    def get_checkpointer(cls):
        cls.ensure_ready()
        return cls._checkpointer
