"""
Main interactive agent loop — reads user input, calls the LLM, dispatches tools.
"""

import json
import re
from typing import Any, Dict

from config import (
	ASSISTANT_COLOR,
	OLLAMA_MODEL,
	RESET_COLOR,
	STATUS_COLOR,
	YOU_COLOR,
	get_ollama_chat_url,
)
from llm_client import execute_llm_call
from parsing import (
	contains_fenced_code_block,
	extract_fenced_tool_invocations_without_prefix,
	extract_tool_invocations,
	looks_like_deferred_work_message,
	user_likely_requested_filesystem_action,
)
from prompts import get_full_system_prompt
from run_logger import log_event
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
	system_prompt = get_full_system_prompt()
	conversation = [{"role": "system", "content": system_prompt}]

	log_event(
		"session.start",
		{
			"model": OLLAMA_MODEL,
			"chat_url": get_ollama_chat_url(),
			"system_prompt": system_prompt,
		},
	)

	try:
		while True:
			try:
				user_input = input(f"{YOU_COLOR}You:{RESET_COLOR}: ")
			except (KeyboardInterrupt, EOFError) as exc:
				log_event("session.stop_signal", {"signal": exc.__class__.__name__})
				print("\nExiting.")
				break

			user_input = user_input.strip()
			if not user_input:
				log_event("user.input.ignored_empty")
				continue

			log_event("user.input", {"text": user_input})
			conversation.append({"role": "user", "content": user_input})
			expects_filesystem_action = user_likely_requested_filesystem_action(user_input)
			malformed_tool_retry_count = 0
			code_block_without_tool_retry_count = 0
			empty_response_retry_count = 0
			deferred_progress_nudge_count = 0

			while True:
				log_event(
					"llm.call.start",
					{
						"conversation_message_count": len(conversation),
						"conversation": conversation,
					},
				)

				raw_response = execute_llm_call(conversation)
				# Strip <think>...</think> blocks for display/logic; keep raw in history
				assistant_response = strip_thinking_tags(raw_response)

				if not assistant_response.strip():
					empty_response_retry_count += 1
					log_event(
						"llm.call.result",
						{
							"raw_response": raw_response,
							"assistant_response": assistant_response,
							"tool_invocations": [],
							"empty_after_strip": True,
							"retry_count": empty_response_retry_count,
						},
					)

					if empty_response_retry_count <= 3:
						print(
							f"{STATUS_COLOR}Status:{RESET_COLOR} Model returned an empty response; nudging it to continue with tools."
						)
						nudge_message = (
							"tool_result({\"error\": \"Assistant returned an empty response (possibly thinking-only output). "
							"Continue the current task and emit the next tool call now. "
							"Your entire response must be a single line: tool: TOOL_NAME({...})\"})"
						)
						conversation.append(
							{
								"role": "user",
								"content": nudge_message,
							}
						)
						log_event("assistant.response.empty.nudge", {"nudge": nudge_message})
						continue

					print(f"{STATUS_COLOR}Status:{RESET_COLOR} Model kept returning empty responses. Try again.")
					log_event("assistant.response.empty.exhausted", {"raw_response": raw_response})
					break

				empty_response_retry_count = 0
				tool_invocations = extract_tool_invocations(assistant_response)
				recovered_fenced_tool_invocations = []

				if (
					not tool_invocations
					and expects_filesystem_action
					and contains_fenced_code_block(assistant_response)
				):
					recovered_fenced_tool_invocations = [
						(name, args)
						for name, args in extract_fenced_tool_invocations_without_prefix(assistant_response)
						if name in TOOL_REGISTRY
					]
					if recovered_fenced_tool_invocations:
						tool_invocations = recovered_fenced_tool_invocations

				conversation.append({"role": "assistant", "content": raw_response})

				log_event(
					"llm.call.result",
					{
						"raw_response": raw_response,
						"assistant_response": assistant_response,
						"tool_invocations": tool_invocations,
						"recovered_fenced_tool_invocations": recovered_fenced_tool_invocations,
					},
				)

				if recovered_fenced_tool_invocations:
					log_event(
						"assistant.response.fenced_tool_recovered",
						{"tool_invocations": recovered_fenced_tool_invocations},
					)

				if not tool_invocations:
					if re.search(r"\btool\s*:", assistant_response, re.IGNORECASE):
						malformed_tool_retry_count += 1
						log_event(
							"assistant.response.malformed_tool",
							{
								"retry_count": malformed_tool_retry_count,
								"assistant_response": assistant_response,
							},
						)

						if malformed_tool_retry_count > 3:
							print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
							print(
								f"{STATUS_COLOR}Status:{RESET_COLOR} Model produced malformed tool calls repeatedly."
							)
							log_event("assistant.response.malformed_tool.exhausted", assistant_response)
							break

						print(
							f"{STATUS_COLOR}Status:{RESET_COLOR} Malformed tool call detected. Asking model to re-emit valid JSON tool call."
						)
						nudge_message = (
							"tool_result({\"error\": \"Malformed tool invocation. "
							"Emit exactly one tool line in strict JSON format with quoted keys. "
							"Example: tool: list_files({\\\"path\\\": \\\".\\\"})\"})"
						)
						conversation.append(
							{
								"role": "user",
								"content": nudge_message,
							}
						)
						log_event("assistant.response.malformed_tool.nudge", {"nudge": nudge_message})
						continue

					if expects_filesystem_action and contains_fenced_code_block(assistant_response):
						code_block_without_tool_retry_count += 1
						log_event(
							"assistant.response.code_block_without_tool",
							{
								"retry_count": code_block_without_tool_retry_count,
								"assistant_response": assistant_response,
								"expects_filesystem_action": expects_filesystem_action,
							},
						)

						if code_block_without_tool_retry_count <= 3:
							print(
								f"{STATUS_COLOR}Status:{RESET_COLOR} Model returned raw code for a file task; nudging it to execute tools."
							)
							nudge_message = (
								"tool_result({\"error\": \"Returned fenced code instead of tool execution for a filesystem task. "
								"Do not return markdown/code fences. Use tool calls now: create_directory if needed, then edit_file with path/new_str. "
								"Emit exactly one line: tool: TOOL_NAME({...})\"})"
							)
							conversation.append(
								{
									"role": "user",
									"content": nudge_message,
								}
							)
							log_event("assistant.response.code_block_without_tool.nudge", {"nudge": nudge_message})
							continue

						print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
						print(
							f"{STATUS_COLOR}Status:{RESET_COLOR} Model kept returning code blocks without tools. Try rephrasing your request."
						)
						log_event("assistant.response.code_block_without_tool.exhausted", assistant_response)
						break

					if looks_like_deferred_work_message(assistant_response):
						deferred_progress_nudge_count += 1
						log_event(
							"assistant.response.deferred",
							{
								"retry_count": deferred_progress_nudge_count,
								"assistant_response": assistant_response,
							},
						)

						if deferred_progress_nudge_count <= 3:
							print(
								f"{STATUS_COLOR}Status:{RESET_COLOR} Apek deferred action; nudging it to execute tools now."
							)
							nudge_message = (
								"Stop narrating. Execute the FIRST required tool call RIGHT NOW. "
								"Your entire response must be a single line: tool: TOOL_NAME({...})"
							)
							conversation.append(
								{
									"role": "user",
									"content": nudge_message,
								}
							)
							log_event("assistant.response.deferred.nudge", {"nudge": nudge_message})
							continue

						# Exhausted nudges — don't silently break, tell the user
						print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
						print(f"{STATUS_COLOR}Status:{RESET_COLOR} Model kept deferring. Try rephrasing your request.")
						log_event("assistant.response.deferred.exhausted", assistant_response)
						break

					print(f"{ASSISTANT_COLOR}Apek:{RESET_COLOR}: {assistant_response}")
					log_event("assistant.response.final_text", {"text": assistant_response})
					break

				malformed_tool_retry_count = 0
				code_block_without_tool_retry_count = 0
				empty_response_retry_count = 0
				deferred_progress_nudge_count = 0

				for name, args in tool_invocations:
					log_event("tool.execution.start", {"name": name, "args": args})

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
					log_event("tool.execution.result", {"name": name, "response": resp})

					print(
						f"{STATUS_COLOR}Tool Result:{RESET_COLOR} {json.dumps(resp, ensure_ascii=False)}"
					)

					conversation.append(
						{
							"role": "user",
							"content": f"tool_result({json.dumps(resp)})",
						}
					)
					log_event(
						"tool.execution.result.appended",
						{
							"name": name,
							"conversation_message_count": len(conversation),
						},
					)
	finally:
		log_event(
			"session.end",
			{
				"conversation_message_count": len(conversation),
			},
		)
