"""
File-system tools available to the coding agent.
"""

import inspect
from pathlib import Path
from typing import Any, Dict


def resolve_abs_path(path_str: str) -> Path:
	"""
	file.py -> /absolute/path/to/current/working/directory/file.py
	"""
	path = Path(path_str).expanduser()
	if not path.is_absolute():
		path = (Path.cwd() / path).resolve()
	return path


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
	Executes a shell command (e.g. 'npm install', 'mkdir').
	:param command: The command to execute in the terminal.
	:return: A dictionary containing stdout and stderr.
	"""
	import subprocess
	try:
		cwd = Path.cwd()
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
