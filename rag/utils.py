"""Utility helpers for rag package.

Implements:
- env_config: simple env var loader with defaults/required checking
- setup_logger: basic logging configuration helper
- retry_backoff: decorator for retries with exponential backoff
- safe_json_loads: parse JSON from string with error handling
- snippet/truncate helpers for building evidence snippets
"""

from typing import Any, Callable, Optional
import os
import json
import logging
import time
import functools


def env_config(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.getenv(key, default)
    if required and not val:
        raise EnvironmentError(f"Required environment variable {key} is not set")
    return val


def setup_logger(name: str = "rag", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def retry_backoff(retries: int = 3, base_delay: float = 0.5, factor: float = 2.0):
    """Decorator to retry a function with exponential backoff on exceptions."""

    def deco(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            delay = base_delay
            for attempt in range(1, retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == retries:
                        raise
                    time.sleep(delay)
                    delay *= factor
            raise last_exc

        return wrapper

    return deco


def safe_json_loads(s: str, default: Any = None) -> Any:
    """Safely parse JSON string, return default on failure and log the error."""
    try:
        return json.loads(s)
    except Exception:
        logging.getLogger("rag.utils").debug("Failed to parse JSON string", exc_info=True)
        return default


def truncate(text: Optional[str], max_len: int = 200) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def make_snippet(text: str, start: int = 0, length: int = 200) -> str:
    if not text:
        return ""
    return truncate(text[start : start + length], length)


