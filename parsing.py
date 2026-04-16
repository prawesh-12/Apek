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
	if re.search(r"\btool\s*:", text, re.IGNORECASE):
		return False

	# Normalize smart punctuation and whitespace so variants like “I’ll” are caught.
	normalized = (
		text.replace("\u2019", "'")
		.replace("\u2018", "'")
		.replace("\u201c", '"')
		.replace("\u201d", '"')
	)
	normalized = re.sub(r"\s+", " ", normalized).strip()
	lower = normalized.lower()

	# Remove common conversational fillers that can precede a deferred action line.
	lower = re.sub(r"^(okay|ok|sure|alright|great|got it|sounds good)[,!.\s:-]+", "", lower)

	# Must start with a deferral phrase
	if not re.search(
		r"^(i\s*(will|'?ll|am\s+going\s+to)|let\s+me|starting\s+now|on\s+it|right\s+away|first\s*,?\s*i\s*(will|'?ll))\b",
		lower,
		re.IGNORECASE,
	):
		return False
	# Actual code block = real content, not deferral
	if "```" in normalized:
		return False
	# Long enough to be a real explanation -> not a deferral
	if len(normalized) > 400:
		return False
	return True


def contains_fenced_code_block(text: str) -> bool:
	"""Return True if response includes at least one fenced code block."""
	return bool(re.search(r"```[A-Za-z0-9_+-]*\n.*?```", text, re.DOTALL))


def user_likely_requested_filesystem_action(user_text: str) -> bool:
	"""
	Heuristic: detect requests that likely require creating/editing files.
	"""
	normalized = re.sub(r"\s+", " ", user_text).strip().lower()
	if not normalized:
		return False

	action_match = re.search(
		r"\b(create|build|make|write|edit|update|modify|save|add|implement|generate|scaffold)\b",
		normalized,
	)
	target_match = re.search(
		r"\b(file|folder|directory|project|app|page|component|script|html|css|js|json|python|py|readme)\b|(?:[a-z0-9._-]+\.[a-z0-9]{1,8}\b)",
		normalized,
	)

	return bool(action_match and target_match)


def extract_fenced_tool_invocations_without_prefix(text: str) -> List[Tuple[str, Dict[str, Any]]]:
	"""
	Recover tool calls from fenced blocks when the model omitted the `tool:` prefix.

	Accepted forms inside fenced code:
	  - tool: create_directory({"path": "demo"})
	  - create_directory({"path": "demo"})
	"""

	def parse_candidate_line(candidate: str) -> Tuple[str, Dict[str, Any]] | None:
		match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", candidate)
		if not match:
			return None

		name = match.group(1)
		json_start = match.end()
		while json_start < len(candidate) and candidate[json_start].isspace():
			json_start += 1

		parsed_args = parse_json_args_maybe_relaxed(candidate[json_start:])
		if parsed_args is None:
			return None

		args, consumed_json = parsed_args
		pos = json_start + consumed_json

		while pos < len(candidate) and candidate[pos].isspace():
			pos += 1
		if pos >= len(candidate) or candidate[pos] != ")":
			return None
		pos += 1

		while pos < len(candidate) and candidate[pos].isspace():
			pos += 1
		if pos < len(candidate) and candidate[pos] == ";":
			pos += 1

		while pos < len(candidate) and candidate[pos].isspace():
			pos += 1
		if pos != len(candidate):
			return None

		return name, args

	recovered: List[Tuple[str, Dict[str, Any]]] = []
	fenced_blocks = re.findall(r"```[A-Za-z0-9_+-]*\n(.*?)```", text, re.DOTALL)

	for block in fenced_blocks:
		for raw_line in block.splitlines():
			line = raw_line.strip()
			if not line:
				continue

			candidate = line
			tool_prefix = re.match(r"^tool\s*:\s*", candidate, re.IGNORECASE)
			if tool_prefix:
				candidate = candidate[tool_prefix.end():].strip()

			# Ignore shell commands and prose; only accept direct function-call lines.
			if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)\s*;?", candidate):
				continue

			parsed = parse_candidate_line(candidate)
			if parsed is not None:
				recovered.append(parsed)

	return recovered


def extract_tool_invocations(text: str) -> List[Tuple[str, Dict[str, Any]]]:
	"""
	Return list of (tool_name, args) requested in 'tool: name({...})' snippets.
	This parser tolerates extra text before/after tool calls on the same line.
	"""

	def parse_tool_call_at(line: str, segment_start: int) -> Tuple[str, Dict[str, Any], int] | None:
		segment = line[segment_start:]
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

		consumed_chars = pos + 1
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
			match = re.search(r"\btool\s*:\s*", line[search_start:], re.IGNORECASE)
			if match is None:
				break

			segment_start = search_start + match.end()

			parsed = parse_tool_call_at(line, segment_start)
			if parsed is None:
				search_start = segment_start
				continue

			name, args, consumed = parsed
			invocations.append((name, args))
			search_start = segment_start + consumed

	return invocations
