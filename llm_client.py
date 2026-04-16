"""
LLM client for communicating with the Ollama-compatible API.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, get_ollama_chat_url


def execute_llm_call(conversation: List[Dict[str, str]]) -> str:
	payload = {
		"model": OLLAMA_MODEL,
		"messages": conversation,
		"stream": False,
	}

	headers = {
		"Content-Type": "application/json",
	}
	if OLLAMA_API_KEY:
		headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

	request = urllib.request.Request(
		url=get_ollama_chat_url(),
		data=json.dumps(payload).encode("utf-8"),
		headers=headers,
		method="POST",
	)

	try:
		with urllib.request.urlopen(request, timeout=300) as response:
			response_text = response.read().decode("utf-8", errors="replace")
			try:
				response_data = json.loads(response_text)
			except json.JSONDecodeError as exc:
				snippet = response_text[:220].replace("\n", " ")
				raise RuntimeError(
					"Ollama returned a non-JSON response. "
					f"Check OLLAMA_BASE_URL/OLLAMA_CHAT_PATH. URL={get_ollama_chat_url()} "
					f"Body starts with: {snippet!r}"
				) from exc
	except urllib.error.HTTPError as exc:
		error_body = exc.read().decode("utf-8", errors="replace")
		raise RuntimeError(f"Ollama API HTTP {exc.code}: {error_body}") from exc
	except urllib.error.URLError as exc:
		raise RuntimeError(
			f"Failed to reach Ollama API at {OLLAMA_BASE_URL}: {exc.reason}"
		) from exc

	assistant_message = response_data.get("message", {})
	assistant_content = assistant_message.get("content")
	if not isinstance(assistant_content, str):
		raise RuntimeError(f"Unexpected Ollama response format: {response_data}")

	return assistant_content
