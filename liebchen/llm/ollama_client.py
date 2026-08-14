"""
Ollama LLM client initialization and health checking.

This module provides a factory function that creates a configured
ChatOllama instance and verifies the Ollama server is reachable,
or falls back to a cloud API (like Groq) if a cloud API key is provided.
"""

from __future__ import annotations

import os
import sys
import urllib.request
import urllib.error
import json
from typing import Any

from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

from liebchen.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TEMPERATURE


def check_ollama_health() -> dict:
    """
    Check if the Ollama server is running and the target model is available.

    Returns:
        A dict with keys: 'server_ok', 'model_available', 'models', 'error'.
    """
    # If using Groq in production, bypass the local Ollama health check
    if os.environ.get("GROQ_API_KEY"):
        return {
            "server_ok": True,
            "model_available": True,
            "models": ["groq-cloud"],
            "error": None,
        }

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
) -> BaseChatModel:
    """
    Create and return a configured Chat Model instance.
    Uses Groq Cloud if GROQ_API_KEY is present (ideal for production),
    otherwise falls back to local Ollama (optimized for fast CPU inference).
    """
    groq_api_key = os.environ.get("GROQ_API_KEY")
    
    if groq_api_key:
        try:
            from langchain_groq import ChatGroq
            # Groq uses Llama 3 models natively. We default to the fastest 8B model.
            groq_model = "llama-3.1-8b-instant" 
            return ChatGroq(
                api_key=groq_api_key,
                model_name=groq_model,
                temperature=temperature if temperature is not None else OLLAMA_TEMPERATURE,
            )
        except ImportError:
            print("⚠️ GROQ_API_KEY is set but langchain-groq is not installed. Falling back to Ollama...")

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


def get_llm_with_health_check(**kwargs) -> BaseChatModel:
    """
    Create a Chat Model instance after verifying health.

    Prints diagnostic info and exits if the server or model is unavailable.
    """
    if os.environ.get("GROQ_API_KEY"):
        print("☁️ Using Groq Cloud API for Inference (GROQ_API_KEY found)")
        return get_llm(**kwargs)
        
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
