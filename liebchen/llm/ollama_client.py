"""
Ollama LLM client initialization and health checking.

This module provides a factory function that creates a configured
ChatOllama instance and verifies the Ollama server is reachable.
"""

from __future__ import annotations

import sys
import urllib.request
import urllib.error
import json

from langchain_ollama import ChatOllama

from liebchen.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TEMPERATURE


def check_ollama_health() -> dict:
    """
    Check if the Ollama server is running and the target model is available.

    Returns:
        A dict with keys: 'server_ok', 'model_available', 'models', 'error'.
    """
    result = {
        "server_ok": False,
        "model_available": False,
        "models": [],
        "error": None,
    }

    # 1. Check server connectivity
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            result["server_ok"] = True
            model_names = [m.get("name", "") for m in data.get("models", [])]
            result["models"] = model_names
    except urllib.error.URLError as e:
        result["error"] = (
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. "
            f"Make sure Ollama is running ('ollama serve'). Error: {e}"
        )
        return result
    except Exception as e:
        result["error"] = f"Unexpected error checking Ollama: {e}"
        return result

    # 2. Check if the configured model is available
    target = OLLAMA_MODEL
    # Ollama model names may or may not include ":latest"
    for name in model_names:
        if name == target or name.startswith(f"{target}:") or target.startswith(f"{name.split(':')[0]}"):
            result["model_available"] = True
            break

    if not result["model_available"]:
        result["error"] = (
            f"Model '{OLLAMA_MODEL}' not found. Available models: {model_names}. "
            f"Pull it with: ollama pull {OLLAMA_MODEL}"
        )

    return result


def get_llm(
    model: str | None = None,
    temperature: float | None = None,
    base_url: str | None = None,
) -> ChatOllama:
    """
    Create and return a configured ChatOllama instance.
    Optimized for fast CPU inference (Ryzen 5 5625U + 12GB RAM).
    """
    return ChatOllama(
        model=model or OLLAMA_MODEL,
        temperature=temperature if temperature is not None else OLLAMA_TEMPERATURE,
        base_url=base_url or OLLAMA_BASE_URL,
        keep_alive="24h",   # FORCE keep alive so HDD doesn't have to read 2-3GB every request
        num_predict=400,     # limit response token length to keep generation fast (< 5s)
        top_k=20,           # limit candidate pool for faster sampling
        top_p=0.8,
        num_ctx=2048,       # smaller context window reduces memory bandwidth pressure
        num_thread=8,       # explicitly bind 8 of 12 Ryzen threads for generation speed
    )


def get_llm_with_health_check(**kwargs) -> ChatOllama:
    """
    Create a ChatOllama instance after verifying Ollama is healthy.

    Prints diagnostic info and exits if the server or model is unavailable.
    """
    print("🔍 Checking Ollama server health...")
    health = check_ollama_health()

    if not health["server_ok"]:
        print(f"❌ {health['error']}")
        sys.exit(1)

    print(f"✅ Ollama server is running at {OLLAMA_BASE_URL}")

    if not health["model_available"]:
        print(f"⚠️  {health['error']}")
        print("   Attempting to continue anyway — Ollama may auto-pull the model.")

    print(f"🤖 Using model: {OLLAMA_MODEL}")
    return get_llm(**kwargs)
