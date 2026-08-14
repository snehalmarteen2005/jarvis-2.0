"""
Single-instance enforcement using Win32 Named Mutex + signal socket.

Why Named Mutex over socket lock:
- OS-native, survives crashes (auto-released when process dies)
- No port conflicts
- The signal socket (port 49998) is used ONLY for IPC, not locking

Flow:
  1. Try to create a named mutex
  2. If it already exists → another instance is running
  3. Send a SHOW signal via socket to the existing instance
  4. Exit gracefully
"""

from __future__ import annotations

import ctypes
import socket
import sys
import threading
import time

from core.constants import MUTEX_NAME, LOCK_PORT, SIGNAL_PORT


def acquire_instance_lock() -> bool:
    """
    Try to become the single running instance.

    Returns True if this is the first instance.
    Returns False if another instance already owns the mutex.
    """
    # CreateMutexW returns a handle; GetLastError() == 183 means it already existed
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()

    if last_error == 183:  # ERROR_ALREADY_EXISTS
        return False

    # Also bind the lock port as a secondary guard
    try:
        global _lock_socket
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(("127.0.0.1", LOCK_PORT))
        _lock_socket.listen(1)
    except socket.error:
        return False

    return True


def signal_existing_instance():
    """Send a SHOW signal to the already-running instance so it surfaces."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("127.0.0.1", SIGNAL_PORT))
        sock.sendall(b"SHOW")
        sock.close()
    except Exception:
        pass


def start_signal_listener(on_show_callback):
    """
    Background thread that listens for SHOW signals from duplicate launches.

    Args:
        on_show_callback: Called (with no args) when a SHOW signal is received.
                          Typically this brings the window to front.
    """
    def _listen():
        try:
            sig_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sig_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sig_sock.bind(("127.0.0.1", SIGNAL_PORT))
            sig_sock.listen(1)
        except Exception:
            return

        while True:
            try:
                conn, _ = sig_sock.accept()
                data = conn.recv(16)
                conn.close()
                if data == b"SHOW":
                    on_show_callback()
            except Exception:
                time.sleep(0.5)

    t = threading.Thread(target=_listen, daemon=True, name="signal-listener")
    t.start()
    return t


def enforce_single_instance():
    """
    Call at the very start of main(). Exits if another instance is running,
    after signaling it to show itself.
    """
    if not acquire_instance_lock():
        print("Jarvis is already running! Bringing existing window to front...")
        signal_existing_instance()
        sys.exit(0)
