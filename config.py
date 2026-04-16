"""
Configuration and environment loading for the coding agent.
"""

import os
from pathlib import Path


def load_env_file(path: Path | None = None) -> None:
	"""
	Loads KEY=VALUE pairs from a local .env file into process environment variables.
	Existing environment variables are not overwritten.
	"""
	if path is None:
		path = Path(__file__).resolve().parent / ".env"

	if not path.exists():
		return

	for raw_line in path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip().strip('"').strip("'")
		if key:
			os.environ.setdefault(key, value)


# Load .env on import
load_env_file()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_CHAT_PATH = os.getenv("OLLAMA_CHAT_PATH", "/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "glm-5.1:cloud")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# Terminal colors
YOU_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
STATUS_COLOR = "\u001b[96m"
RESET_COLOR = "\u001b[0m"


def get_ollama_chat_url() -> str:
	if OLLAMA_CHAT_PATH.startswith("http://") or OLLAMA_CHAT_PATH.startswith("https://"):
		return OLLAMA_CHAT_PATH
	if OLLAMA_CHAT_PATH.startswith("/"):
		return f"{OLLAMA_BASE_URL}{OLLAMA_CHAT_PATH}"
	return f"{OLLAMA_BASE_URL}/{OLLAMA_CHAT_PATH}"
