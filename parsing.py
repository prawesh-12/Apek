"""
Parsing utilities for extracting tool calls from LLM responses.
"""

import json
import re
from typing import Any, Dict, List, Tuple


def parse_json_args_maybe_relaxed(raw_text: str) -> Tuple[Dict[str, Any], int] | None:
	"""
	Parse JSON args from the start of raw_text.
	First try strict JSON, then a relaxed mode that quotes bare keys and accepts single quotes.
	Returns (args_dict, consumed_chars) or None.
	"""
	try:
		parsed, consumed = json.JSONDecoder().raw_decode(raw_text)
		if isinstance(parsed, dict):
			return parsed, consumed
	except json.JSONDecodeError:
		pass

	leading_ws = len(raw_text) - len(raw_text.lstrip())
	candidate = raw_text.lstrip()
	if not candidate.startswith("{"):
		return None

	# Find the matching closing brace for the first object while honoring quotes.
	depth = 0
	in_string = False
	escaped = False
	quote_char = ""
	end_idx = -1
	for idx, ch in enumerate(candidate):
		if in_string:
			if escaped:
				escaped = False
			elif ch == "\\":
				escaped = True
			elif ch == quote_char:
				in_string = False
			continue

		if ch == '"' and idx > 0 and (candidate[idx - 1].isalnum() or candidate[idx - 1] == "_"):
			look_ahead = idx + 1
			while look_ahead < len(candidate) and candidate[look_ahead].isspace():
				look_ahead += 1
			if look_ahead < len(candidate) and candidate[look_ahead] == ":":
				# malformed key quote in patterns like {path": ...}; ignore as quote delimiter.
				continue

		if ch in ('"', "'"):
			in_string = True
			quote_char = ch
			continue
		if ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				end_idx = idx
				break

	if end_idx == -1:
		return None

	object_text = candidate[: end_idx + 1]
	normalized = object_text
	# quote bare keys: {path: "."} -> {"path": "."}
	normalized = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', normalized)
	# fix partially quoted keys: {path": "."} -> {"path": "."}
	normalized = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\"(\s*:)", r'\1"\2"\3', normalized)
	# allow single-quoted strings in malformed tool calls.
	normalized = normalized.replace("'", '"')

	try:
		parsed = json.loads(normalized)
	except json.JSONDecodeError:
		return None

	if not isinstance(parsed, dict):
		return None

	consumed_chars = leading_ws + end_idx + 1
	return parsed, consumed_chars


def summarize_tool_result(tool_name: str, response: Dict[str, Any]) -> str:
	if tool_name == "read_file" and "file_path" in response and "content" in response:
		return f"read {response['file_path']} ({len(response['content'])} chars)"
	if tool_name == "list_files" and "path" in response and isinstance(response.get("files"), list):
		return f"listed {response['path']} ({len(response['files'])} entries)"
	if tool_name == "edit_file" and "path" in response and "action" in response:
		return f"{response['action']} -> {response['path']}"

	text = json.dumps(response, ensure_ascii=False)
	return text if len(text) <= 220 else text[:220] + "..."


def looks_like_deferred_work_message(text: str) -> bool:
	"""
	Return True when the model responded with pure planning narration instead of
	calling a tool.  Criteria (ALL must hold):
	  1. No tool call present.
	  2. Starts with a known deferral phrase (anchored to ^ so mid-sentence "I'll"
	     in a real answer doesn't trigger this).
	  3. No code blocks — code fences are real content.  Plan lists ("1. do X"
	     or "- do X") are still deferral, not real content.
	  4. Under 400 chars — covers multi-sentence planning narration but not a
	     genuine multi-paragraph technical explanation.
	"""
	if "tool:" in text:
		return False
	# Must start with a deferral phrase
	if not re.search(r"^\s*(i\s*will|i\s*'?ll|let me|starting now|on it|right away)\b", text, re.IGNORECASE):
		return False
	# Actual code block = real content, not deferral
	if "```" in text:
		return False
	# Long enough to be a real explanation -> not a deferral
	if len(text.strip()) > 400:
		return False
	return True


def extract_tool_invocations(text: str) -> List[Tuple[str, Dict[str, Any]]]:
	"""
	Return list of (tool_name, args) requested in 'tool: name({...})' snippets.
	This parser tolerates extra text before/after tool calls on the same line.
	"""

	def parse_tool_call_at(line: str, start_idx: int) -> Tuple[str, Dict[str, Any], int] | None:
		segment = line[start_idx + len("tool:") :]
		match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", segment)
		if not match:
			return None

		name = match.group(1)
		json_start = match.end()
		while json_start < len(segment) and segment[json_start].isspace():
			json_start += 1

		parsed_args = parse_json_args_maybe_relaxed(segment[json_start:])
		if parsed_args is None:
			return None
		args, consumed_json = parsed_args

		pos = json_start + consumed_json
		while pos < len(segment) and segment[pos].isspace():
			pos += 1
		if pos >= len(segment) or segment[pos] != ")":
			return None

		consumed_chars = len("tool:") + pos + 1
		return name, args, consumed_chars

	invocations = []
	
	# 1. First, look for markdown JSON blocks containing tool calls
	json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
	if not json_blocks:
		# If no code blocks, maybe there's raw JSON object around the text (some LLMs output raw JSON)
		raw_match = re.search(r"^\s*(\{.*?\})\s*$", text, re.DOTALL)
		if raw_match:
			json_blocks.append(raw_match.group(1))

	for block in json_blocks:
		try:
			data = json.loads(block)
			if isinstance(data, dict) and "tool" in data:
				name = data["tool"]
				args = data.get("args", {})
				invocations.append((name, args))
		except json.JSONDecodeError:
			pass

	# If we found tool calls in markdown JSON, return those, otherwise fall back to old parser
	if invocations:
		return invocations

	# 2. Fall back to parsing inline "tool: name({...})" formats
	for raw_line in text.splitlines():
		line = raw_line.strip()
		search_start = 0
		while True:
			idx = line.find("tool:", search_start)
			if idx == -1:
				break

			parsed = parse_tool_call_at(line, idx)
			if parsed is None:
				search_start = idx + len("tool:")
				continue

			name, args, consumed = parsed
			invocations.append((name, args))
			search_start = idx + consumed

	return invocations
