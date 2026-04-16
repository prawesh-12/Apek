"""
Main interactive agent loop — reads user input, calls the LLM, dispatches tools.
"""

import json
import re
from typing import Any, Dict

from config import ASSISTANT_COLOR, RESET_COLOR, STATUS_COLOR, YOU_COLOR
from llm_client import execute_llm_call
from parsing import (
	extract_tool_invocations,
	looks_like_deferred_work_message,
)
from prompts import get_full_system_prompt
from tools import TOOL_REGISTRY


def strip_thinking_tags(text: str) -> str:
	"""Remove <think>...</think> blocks that Qwen3 thinking models emit."""
	return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
	"""Dispatch a parsed tool call to the correct handler."""
	tool = TOOL_REGISTRY.get(name)
	if tool is None:
		return {"error": f"Unknown tool: {name}"}

	try:
		return tool(**args)
	except Exception as exc:
		return {"error": str(exc), "tool": name, "args": args}


def run_coding_agent_loop() -> None:
	conversation = [{"role": "system", "content": get_full_system_prompt()}]

	while True:
		try:
			user_input = input(f"{YOU_COLOR}You:{RESET_COLOR}: ")
		except (KeyboardInterrupt, EOFError):
			print("\nExiting.")
			break

		user_input = user_input.strip()
		if not user_input:
			continue

		conversation.append({"role": "user", "content": user_input})
		malformed_tool_retry_count = 0
		deferred_progress_nudge_count = 0

		while True:
			raw_response = execute_llm_call(conversation)
			# Strip <think>...</think> blocks for display/logic; keep raw in history
			assistant_response = strip_thinking_tags(raw_response)
			tool_invocations = extract_tool_invocations(assistant_response)
			conversation.append({"role": "assistant", "content": raw_response})

			if not tool_invocations:
				if "tool:" in assistant_response:
					malformed_tool_retry_count += 1
					if malformed_tool_retry_count > 3:
						print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
						print(
							f"{STATUS_COLOR}Status:{RESET_COLOR} Model produced malformed tool calls repeatedly."
						)
						break

					print(
						f"{STATUS_COLOR}Status:{RESET_COLOR} Malformed tool call detected. Asking model to re-emit valid JSON tool call."
					)
					conversation.append(
						{
							"role": "user",
							"content": (
								"tool_result({\"error\": \"Malformed tool invocation. "
								"Emit exactly one tool line in strict JSON format with quoted keys. "
								"Example: tool: list_files({\\\"path\\\": \\\".\\\"})\"})"
							),
						}
					)
					continue

				if looks_like_deferred_work_message(assistant_response):
					deferred_progress_nudge_count += 1
					if deferred_progress_nudge_count <= 3:
						print(
							f"{STATUS_COLOR}Status:{RESET_COLOR} Apek deferred action; nudging it to execute tools now."
						)
						conversation.append(
							{
								"role": "user",
								"content": (
									"Stop narrating. Execute the FIRST required tool call RIGHT NOW. "
									"Your entire response must be a single line: tool: TOOL_NAME({...})"
								),
							}
						)
						continue
					# Exhausted nudges — don't silently break, tell the user
					print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
					print(f"{STATUS_COLOR}Status:{RESET_COLOR} Model kept deferring. Try rephrasing your request.")
					break

				print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
				break

			malformed_tool_retry_count = 0
			deferred_progress_nudge_count = 0

			for name, args in tool_invocations:
				# Format args for console display cleanly. Truncate long strings for readability.
				display_dict = {}
				for k, v in args.items():
					if isinstance(v, str) and len(v) > 100:
						display_dict[k] = v[:97] + "..." + f" [<folded {len(v)} chars>]"
					else:
						display_dict[k] = v
				
				formatted_args = json.dumps(display_dict, indent=2, ensure_ascii=False)
				
				print(f"\n{STATUS_COLOR}┌── Tool Execution: {name}{RESET_COLOR}")
				for line in formatted_args.splitlines():
					print(f"{STATUS_COLOR}│{RESET_COLOR} {line}")
				print(f"{STATUS_COLOR}└──────────────────────────────────────{RESET_COLOR}")
				
				resp = _dispatch_tool(name, args)

				print(
					f"{STATUS_COLOR}Tool Result:{RESET_COLOR} {json.dumps(resp, ensure_ascii=False)}"
				)

				conversation.append(
					{
						"role": "user",
						"content": f"tool_result({json.dumps(resp)})",
					}
				)
