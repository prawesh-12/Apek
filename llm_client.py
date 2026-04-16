"""
LLM client for communicating with the Ollama-compatible API.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, get_ollama_chat_url
from run_logger import log_event, mask_auth_headers


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

	log_event(
		"llm.request",
		{
			"url": get_ollama_chat_url(),
			"payload": payload,
			"headers": mask_auth_headers(headers),
		},
	)

	request = urllib.request.Request(
		url=get_ollama_chat_url(),
		data=json.dumps(payload).encode("utf-8"),
		headers=headers,
		method="POST",
	)

	try:
		with urllib.request.urlopen(request, timeout=300) as response:
			response_text = response.read().decode("utf-8", errors="replace")
			log_event(
				"llm.response.raw",
				{
					"status": response.status,
					"body": response_text,
				},
			)
			try:
				response_data = json.loads(response_text)
			except json.JSONDecodeError as exc:
				snippet = response_text[:220].replace("\n", " ")
				log_event(
					"llm.response.decode_error",
					{
						"error": str(exc),
						"body_start": snippet,
					},
				)
				raise RuntimeError(
					"Ollama returned a non-JSON response. "
					f"Check OLLAMA_BASE_URL/OLLAMA_CHAT_PATH. URL={get_ollama_chat_url()} "
					f"Body starts with: {snippet!r}"
				) from exc
	except urllib.error.HTTPError as exc:
		error_body = exc.read().decode("utf-8", errors="replace")
		log_event(
			"llm.http_error",
			{
				"status": exc.code,
				"error_body": error_body,
			},
		)
		raise RuntimeError(f"Ollama API HTTP {exc.code}: {error_body}") from exc
	except urllib.error.URLError as exc:
		log_event(
			"llm.connection_error",
			{
				"base_url": OLLAMA_BASE_URL,
				"reason": str(exc.reason),
			},
		)
		raise RuntimeError(
			f"Failed to reach Ollama API at {OLLAMA_BASE_URL}: {exc.reason}"
		) from exc

	assistant_message = response_data.get("message", {})
	assistant_content = assistant_message.get("content")
	if not isinstance(assistant_content, str):
		log_event("llm.response.unexpected_format", response_data)
		raise RuntimeError(f"Unexpected Ollama response format: {response_data}")

	log_event(
		"llm.response.assistant_content",
		{
			"chars": len(assistant_content),
			"content": assistant_content,
		},
	)

	return assistant_content
