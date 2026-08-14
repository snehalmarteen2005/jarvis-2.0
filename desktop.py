import sys
import threading
import time
import os
import uvicorn
import webview
import speech_recognition as sr
import winsound
import socket
from dotenv import load_dotenv

load_dotenv()

# Fix for pythonw.exe (no stdout/stderr causes print() to crash)
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

window = None

# ═══════════════════════════════════════════════════════════════════════════════
#  Single-Instance Enforcement
# ═══════════════════════════════════════════════════════════════════════════════
LOCK_PORT = 49999
SIGNAL_PORT = 49998  # Secondary port to signal the existing instance to show

_lock_socket = None


def try_acquire_lock():
    """Try to bind the lock port. Returns True if we are the first instance."""
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(('127.0.0.1', LOCK_PORT))
        _lock_socket.listen(1)
        return True
    except socket.error:
        return False


def signal_existing_instance():
    """Send a wake-up signal to the already-running Jarvis instance."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(('127.0.0.1', SIGNAL_PORT))
        sock.sendall(b'SHOW')
        sock.close()
        print("Sent SHOW signal to existing Jarvis instance.")
    except Exception as e:
        print(f"Could not signal existing instance: {e}")


def listen_for_show_signal():
    """Background thread: listens for SHOW signals from duplicate launches."""
    global window
    try:
        sig_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sig_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sig_sock.bind(('127.0.0.1', SIGNAL_PORT))
        sig_sock.listen(1)
    except Exception as e:
        print(f"Could not start signal listener: {e}")
        return

    while True:
        try:
            conn, _ = sig_sock.accept()
            data = conn.recv(16)
            conn.close()
            if data == b'SHOW':
                print("Received SHOW signal — bringing window to front.")
                _show_window()
        except Exception:
            time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
#  Ollama + Server
# ═══════════════════════════════════════════════════════════════════════════════


def start_ollama():
    """Ensure Ollama is running in the background."""
    import urllib.request
    import subprocess
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/", timeout=1)
    except Exception:
        try:
            subprocess.Popen("ollama serve", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
        except Exception:
            pass


def start_server():
    """Run the FastAPI server."""
    from liebchen.api.server import app
    uvicorn.run(app, host="127.0.0.1", port=8888, log_level="error")


# ═══════════════════════════════════════════════════════════════════════════════
#  Window Helpers
# ═══════════════════════════════════════════════════════════════════════════════

# Cooldown to prevent rapid-fire activations
_last_activation_time = 0.0
_ACTIVATION_COOLDOWN = 3.0  # seconds


def _show_window():
    """Safely show and bring the window to front, with cooldown."""
    global _last_activation_time, window
    now = time.time()

    # Enforce cooldown — ignore duplicate triggers within 3 seconds
    if now - _last_activation_time < _ACTIVATION_COOLDOWN:
        return

    _last_activation_time = now

    if window:
        try:
            window.show()
            window.restore()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Background Voice Listener (Optimized)
# ═══════════════════════════════════════════════════════════════════════════════

def background_listener():
    """
    Continuously listens for the 'Jarvis' wake word and shows the window.
    
    Optimizations vs. the old version:
      - Keeps the microphone stream open persistently (no re-init per loop)
      - Uses a lower energy_threshold + dynamic adjustment (no blocking calibration)
      - Uses a short phrase_time_limit (2s) for wake-word detection (faster response)
      - 3-second cooldown between activations prevents duplicate triggers
      - Errors are swallowed with a small sleep to avoid CPU spin
    """
    global window
    recognizer = sr.Recognizer()

    # Tune recognizer for responsiveness — avoid the blocking
    # adjust_for_ambient_noise() call inside the hot loop
    recognizer.energy_threshold = 300  # reasonable default for most mics
    recognizer.dynamic_energy_threshold = True  # auto-adjusts over time
    recognizer.pause_threshold = 0.8  # quicker end-of-speech detection

    while True:
        try:
            # Keep the mic open for the entire listen cycle
            with sr.Microphone() as source:
                # One-time calibration on each fresh mic open (0.5s is enough)
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

                while True:
                    try:
                        # Listen for short utterances only (wake word is 1-2 words)
                        audio = recognizer.listen(
                            source,
                            timeout=2,          # wait up to 2s for speech to start
                            phrase_time_limit=2  # max 2s of speech (just the wake word)
                        )
                    except sr.WaitTimeoutError:
                        # No speech detected within timeout — loop and try again
                        continue

                    # Send to Google STT
                    try:
                        text = recognizer.recognize_google(audio).lower()
                    except sr.UnknownValueError:
                        continue  # unintelligible audio
                    except sr.RequestError:
                        time.sleep(2)  # network issue, back off
                        continue

                    # ── Wake word detected ──
                    if "jarvis" in text:
                        winsound.PlaySound(
                            "SystemAsterisk",
                            winsound.SND_ALIAS | winsound.SND_ASYNC
                        )
                        _show_window()

                        # Now listen for the user's actual command
                        try:
                            command_audio = recognizer.listen(
                                source,
                                timeout=5,
                                phrase_time_limit=15
                            )
                            command_text = recognizer.recognize_google(command_audio)

                            if window and command_text:
                                safe_cmd = (
                                    command_text
                                    .replace('\\', '\\\\')
                                    .replace('"', '\\"')
                                    .replace("'", "\\'")
                                )
                                window.evaluate_js(f'''
                                    document.getElementById("msg-input").value = "{safe_cmd}";
                                    document.getElementById("btn-send").disabled = false;
                                    document.getElementById("btn-send").click();
                                ''')
                        except (sr.WaitTimeoutError, sr.UnknownValueError):
                            pass  # user didn't say a follow-up command

                    elif "stop" in text:
                        if window:
                            window.evaluate_js(
                                'if (typeof stopThinking === "function") stopThinking();'
                            )

                    elif "shut down" in text or "go to sleep" in text:
                        winsound.PlaySound(
                            "SystemExit",
                            winsound.SND_ALIAS | winsound.SND_ASYNC
                        )
                        print("Shutting down Jarvis completely...")
                        if window:
                            window.destroy()
                        os._exit(0)

        except Exception:
            # If the mic fails or something unexpected happens,
            # wait a moment and re-open it
            time.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Window Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

def on_closing():
    """When user clicks X, hide the window instead of destroying the app."""
    global window
    window.hide()
    return False


class Api:
    def quit(self):
        """Completely shut down the application and background listener."""
        print("Shutting down Jarvis completely...")
        global window
        if window:
            window.destroy()
        os._exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # ── Single-instance guard ──
    if not try_acquire_lock():
        # Another instance is already running — signal it to show its window
        print("Jarvis is already running! Bringing existing window to front...")
        signal_existing_instance()
        sys.exit(0)

    if not os.environ.get("OLLAMA_MODEL"):
        os.environ["OLLAMA_MODEL"] = "llama3.2"

    start_ollama()

    # Start signal listener (receives SHOW from duplicate launches)
    signal_thread = threading.Thread(target=listen_for_show_signal, daemon=True)
    signal_thread.start()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Start the permanent background voice listener
    listener_thread = threading.Thread(target=background_listener, daemon=True)
    listener_thread.start()

    time.sleep(1.5)

    window = webview.create_window(
        title='Jarvis Assistant',
        url='http://127.0.0.1:8888',
        width=1100,
        height=800,
        resizable=True,
        text_select=True,
        zoomable=True,
        hidden=True,
        js_api=Api()
    )

    window.events.closing += on_closing
    webview.start()
