"""
Command security — whitelist/blacklist validation and prompt injection protection.

Prevents the LLM from being tricked into running destructive commands
like `format C:`, `del /s`, or downloading malicious files.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path

log = logging.getLogger("tools.security")


# ═══════════════════════════════════════════════════════════════════════════════
#  Blocked Commands & Patterns
# ═══════════════════════════════════════════════════════════════════════════════

BLOCKED_COMMANDS = frozenset({
    "format",
    "del /s",
    "rmdir /s",
    "rm -rf",
    "reg delete",
    "bcdedit",
    "diskpart",
    "net user",
    "net localgroup",
    "cipher /w",
    "sfc /scannow",       # requires admin
    "chkdsk",             # requires admin
})

BLOCKED_PATTERNS = [
    r"powershell\s+-enc",                   # encoded commands = obfuscation
    r"Invoke-WebRequest.*-OutFile",         # downloading executables
    r"Start-Process.*-Verb\s+RunAs",        # privilege escalation
    r"Set-ExecutionPolicy",
    r"Disable-.*Firewall",
    r"Remove-Item\s+-Recurse\s+-Force",     # recursive force delete
    r"Stop-Service",
    r"Disable-.*Defender",
    r"New-Service",
    r"Clear-EventLog",
]

# Directories the assistant is allowed to read/write
ALLOWED_DIRECTORIES = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Pictures",
    Path.home() / "Music",
    Path.home() / "Videos",
]


def is_command_safe(command: str) -> tuple[bool, str]:
    """
    Check if a shell command is safe to execute.

    Returns:
        (True, "") if safe
        (False, reason) if blocked
    """
    cmd_lower = command.lower().strip()

    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            reason = f"Blocked command detected: '{blocked}'"
            log.warning(f"SECURITY: {reason} in '{command}'")
            return False, reason

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            reason = f"Blocked pattern matched: '{pattern}'"
            log.warning(f"SECURITY: {reason} in '{command}'")
            return False, reason

    return True, ""


def is_path_allowed(path: str) -> bool:
    """Check if a file path is within allowed directories."""
    try:
        resolved = Path(path).resolve()
        return any(resolved.is_relative_to(d) for d in ALLOWED_DIRECTORIES)
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Prompt Injection Protection
# ═══════════════════════════════════════════════════════════════════════════════

_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+",
    r"system:\s*",
    r"<\|system\|>",
    r"\[INST\]",
    r"\[/INST\]",
    r"<<SYS>>",
    r"<</SYS>>",
    r"forget\s+(?:all\s+)?(?:your\s+)?instructions",
    r"act\s+as\s+(?:if\s+you\s+are|a)\s+",
    r"pretend\s+(?:you\s+are|to\s+be)\s+",
]


def sanitize_input(text: str) -> str:
    """
    Strip prompt injection attempts from user input.
    Replaces suspicious patterns with [FILTERED].
    """
    sanitized = text
    for pattern in _INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)

    if sanitized != text:
        log.warning(f"Prompt injection filtered: '{text[:80]}...'")

    return sanitized
