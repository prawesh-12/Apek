"""
Runtime logger for per-run debug traces.

Logging is enabled when APEK_RUN_LOG_FILE is set.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict

_LOG_FILE_ENV = "APEK_RUN_LOG_FILE"
_LOG_FILE_PATH = os.getenv(_LOG_FILE_ENV, "").strip()
_LOG_LOCK = Lock()
_LOG_BOOTSTRAPPED = False


def _iso_now_utc() -> str:
	return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _format_value(value: Any) -> str:
	try:
		return json.dumps(value, ensure_ascii=False, indent=2, default=str)
	except Exception:
		return repr(value)


def _resolve_log_path() -> Path | None:
	global _LOG_BOOTSTRAPPED

	if not _LOG_FILE_PATH:
		return None

	path = Path(_LOG_FILE_PATH).expanduser()
	try:
		path.parent.mkdir(parents=True, exist_ok=True)
		if not path.exists():
			path.touch()
		if not _LOG_BOOTSTRAPPED:
			with path.open("a", encoding="utf-8") as f:
				f.write(f"[{_iso_now_utc()}] logger.bootstrap\n")
			_LOG_BOOTSTRAPPED = True
		return path
	except Exception:
		# Logging should never crash runtime behavior.
		return None


def mask_auth_headers(headers: Dict[str, str]) -> Dict[str, str]:
	"""Mask secrets from headers before writing logs."""
	sanitized = dict(headers)
	auth_value = sanitized.get("Authorization", "")
	if auth_value:
		if auth_value.lower().startswith("bearer "):
			token = auth_value[7:]
			if len(token) >= 12:
				sanitized["Authorization"] = f"Bearer {token[:6]}...{token[-4:]}"
			else:
				sanitized["Authorization"] = "Bearer ***"
		else:
			sanitized["Authorization"] = "***"
	return sanitized


def log_event(event: str, payload: Any | None = None) -> None:
	"""Append one timestamped event to the active run log file."""
	path = _resolve_log_path()
	if path is None:
		return

	lines = [f"[{_iso_now_utc()}] {event}\n"]
	if payload is not None:
		lines.append(_format_value(payload))
		lines.append("\n")
	lines.append("\n")

	try:
		with _LOG_LOCK:
			with path.open("a", encoding="utf-8") as f:
				f.writelines(lines)
	except Exception:
		# Logging should never crash runtime behavior.
		return
