"""
File-system tools available to the coding agent.
"""

import inspect
import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict


ENV_PROJECTS_ROOT_KEYS = ("APEK_PROJECTS_ROOT", "PROJECTS_ROOT")
DEFAULT_PROJECTS_ROOT = Path("/projects").resolve()
FALLBACK_PROJECTS_ROOT = (Path.home() / "projects").resolve()
_ACTIVE_PROJECTS_ROOT: Path | None = None
CD_COMMAND_RE = re.compile(r"(?:^|[;&|]\s*)cd\s+([^;&|]+)")


def _prepare_projects_root(root: Path) -> Path:
	"""Ensure root exists, is a directory, and is writable."""
	root.mkdir(parents=True, exist_ok=True)
	if not root.is_dir():
		raise RuntimeError(f"Configured projects root is not a directory: {root}")

	probe = root / ".apek_write_probe"
	probe.write_text("ok", encoding="utf-8")
	probe.unlink(missing_ok=True)

	return root


def _get_env_projects_root() -> str:
	for env_key in ENV_PROJECTS_ROOT_KEYS:
		value = os.getenv(env_key, "").strip()
		if value:
			return value
	return ""


def get_projects_root() -> Path:
	"""Ensure the configured projects root exists and return it."""
	global _ACTIVE_PROJECTS_ROOT
	if _ACTIVE_PROJECTS_ROOT is not None:
		return _ACTIVE_PROJECTS_ROOT

	env_root = _get_env_projects_root()
	if env_root:
		candidate = Path(env_root).expanduser().resolve()
		try:
			_ACTIVE_PROJECTS_ROOT = _prepare_projects_root(candidate)
			return _ACTIVE_PROJECTS_ROOT
		except Exception as exc:
			raise RuntimeError(
				f"Configured projects root '{candidate}' is not usable: {exc}"
			) from exc

	try:
		_ACTIVE_PROJECTS_ROOT = _prepare_projects_root(DEFAULT_PROJECTS_ROOT)
		return _ACTIVE_PROJECTS_ROOT
	except Exception as primary_exc:
		try:
			_ACTIVE_PROJECTS_ROOT = _prepare_projects_root(FALLBACK_PROJECTS_ROOT)
			return _ACTIVE_PROJECTS_ROOT
		except Exception as fallback_exc:
			raise RuntimeError(
				f"Could not access default projects root at {DEFAULT_PROJECTS_ROOT}: {primary_exc}. "
				f"Fallback root at {FALLBACK_PROJECTS_ROOT} also failed: {fallback_exc}"
			) from fallback_exc


def _is_within_projects_root(path: Path, projects_root: Path) -> bool:
	return path == projects_root or projects_root in path.parents


def _normalize_shell_token(token: str) -> str:
	return token.strip().strip('"').strip("'")


def _validate_command_scope(command: str, projects_root: Path) -> str | None:
	"""
	Best-effort guard against shell commands that try to operate outside the active projects root.
	"""
	for match in CD_COMMAND_RE.finditer(command):
		raw_target = _normalize_shell_token(match.group(1))
		if not raw_target:
			continue
		if any(mark in raw_target for mark in ("$", "`", "~")):
			return (
				f"Dynamic cd target '{raw_target}' is not allowed. "
				f"Use explicit paths under {projects_root}."
			)

		target_path = Path(raw_target)
		resolved_target = (
			target_path.resolve()
			if target_path.is_absolute()
			else (projects_root / target_path).resolve()
		)
		if not _is_within_projects_root(resolved_target, projects_root):
			return f"Command attempts to change directory outside {projects_root}: {raw_target}"

	try:
		tokens = shlex.split(command)
	except ValueError:
		return (
			"Command parsing failed. Use simpler quoted commands with explicit paths "
			f"under {projects_root}."
		)

	for token in tokens:
		normalized = _normalize_shell_token(token)
		if not normalized:
			continue

		if normalized.startswith("~"):
			return f"Home-directory paths are not allowed. Use paths under {projects_root}."

		if normalized == ".." or normalized.startswith("../") or "/../" in normalized:
			return f"Parent-directory traversal is not allowed outside {projects_root}."

		candidates = [normalized]
		if "=" in normalized:
			_, rhs = normalized.split("=", 1)
			if rhs:
				candidates.append(rhs)

		for candidate in candidates:
			if candidate.startswith("/"):
				resolved = Path(candidate).resolve()
				if not _is_within_projects_root(resolved, projects_root):
					return (
						f"Absolute path '{candidate}' is outside allowed root {projects_root}."
					)

	return None


def resolve_abs_path(path_str: str) -> Path:
	"""
	Resolve to an absolute path that must stay inside the active projects root.
	"""
	projects_root = get_projects_root()
	path = Path(path_str).expanduser()
	resolved = path.resolve() if path.is_absolute() else (projects_root / path).resolve()

	if not _is_within_projects_root(resolved, projects_root):
		raise ValueError(
			f"Path '{resolved}' is outside the allowed projects root '{projects_root}'."
		)

	return resolved


def read_file_tool(filename: str) -> Dict[str, Any]:
	"""
	Gets the full content of a file provided by the user.
	:param filename: The name of the file to read.
	:return: The full content of the file.
	"""
	full_path = resolve_abs_path(filename)
	with open(str(full_path), "r", encoding="utf-8") as f:
		content = f.read()
	return {"file_path": str(full_path), "content": content}


def list_files_tool(path: str) -> Dict[str, Any]:
	"""
	Lists the files in a directory provided by the user.
	:param path: The path to a directory to list files from.
	:return: A list of files in the directory.
	"""
	full_path = resolve_abs_path(path)
	all_files = []
	for item in full_path.iterdir():
		all_files.append(
			{
				"filename": item.name,
				"type": "file" if item.is_file() else "dir",
			}
		)
	return {"path": str(full_path), "files": all_files}


def edit_file_tool(path: str, old_str: str, new_str: str) -> Dict[str, Any]:
	"""
	Replaces first occurrence of old_str with new_str in file. If old_str is empty,
	create/overwrite file with new_str.
	:param path: The path to the file to edit.
	:param old_str: The string to replace.
	:param new_str: The string to replace with.
	:return: A dictionary with the path to the file and the action taken.
	"""
	full_path = resolve_abs_path(path)
	if old_str == "":
		full_path.parent.mkdir(parents=True, exist_ok=True)
		full_path.write_text(new_str, encoding="utf-8")
		return {"path": str(full_path), "action": "created_file"}

	original = full_path.read_text(encoding="utf-8")
	if original.find(old_str) == -1:
		return {"path": str(full_path), "action": "old_str not found"}

	edited = original.replace(old_str, new_str, 1)
	full_path.write_text(edited, encoding="utf-8")
	return {"path": str(full_path), "action": "edited"}


def create_directory_tool(path: str) -> Dict[str, Any]:
	"""
	Creates a new directory (and any necessary parent directories).
	:param path: The path of the directory to create.
	:return: A dictionary confirming creation.
	"""
	full_path = resolve_abs_path(path)
	try:
		full_path.mkdir(parents=True, exist_ok=True)
		return {"path": str(full_path), "action": "created_directory"}
	except Exception as exc:
		return {"error": str(exc), "path": path}


def execute_command_tool(command: str) -> Dict[str, Any]:
	"""
	Executes a shell command inside the active projects root (e.g. 'npm install', 'mkdir').
	:param command: The command to execute in the terminal.
	:return: A dictionary containing stdout and stderr.
	"""
	import subprocess
	try:
		cwd = get_projects_root()
		scope_error = _validate_command_scope(command, cwd)
		if scope_error:
			return {"error": scope_error, "command": command}

		result = subprocess.run(
			command,
			shell=True,
			cwd=cwd,
			capture_output=True,
			text=True,
			timeout=120
		)
		return {
			"command": command,
			"returncode": result.returncode,
			"stdout": result.stdout.strip(),
			"stderr": result.stderr.strip()
		}
	except Exception as exc:
		return {"error": str(exc), "command": command}

# Tool registry

TOOL_REGISTRY = {
	"read_file": read_file_tool,
	"list_files": list_files_tool,
	"edit_file": edit_file_tool,
	"create_directory": create_directory_tool,
	"execute_command": execute_command_tool,
}


def get_tool_str_representation(tool_name: str) -> str:
	tool = TOOL_REGISTRY[tool_name]
	return f"""
Name: {tool_name}
Description: {tool.__doc__}
Signature: {inspect.signature(tool)}
""".strip()
