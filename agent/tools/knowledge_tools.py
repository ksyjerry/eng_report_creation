"""
지식 도구 — Skill Document 읽기 + Working Memory 관리.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent.tools import tool


_working_memory = None
_skills_dir = None


def set_memory(memory) -> None:
    global _working_memory
    _working_memory = memory


def set_skills_dir(path: str) -> None:
    global _skills_dir
    _skills_dir = path


def _get_memory():
    if _working_memory is None:
        raise RuntimeError("WorkingMemory not initialized")
    return _working_memory


@tool("read_skill", "스킬 문서를 읽어 반환합니다. 전문 지식 참조용.")
def read_skill(skill_path: str) -> str:
    """agent_skills/ 내 md 파일을 읽어 반환."""
    if _skills_dir is None:
        return "ERROR: skills_dir not configured"

    full_path = os.path.join(_skills_dir, skill_path)
    if not os.path.exists(full_path):
        return f"ERROR: Skill file not found: {skill_path}"

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 너무 길면 truncate
        if len(content) > 5000:
            content = content[:5000] + "\n\n... (truncated)"
        return content
    except Exception as e:
        return f"ERROR: {e}"


@tool("list_skills", "사용 가능한 스킬 문서 목록을 반환합니다.")
def list_skills() -> str:
    """agent_skills/ 내 모든 md 파일 목록."""
    if _skills_dir is None:
        return "ERROR: skills_dir not configured"

    skills = []
    for root, dirs, files in os.walk(_skills_dir):
        for f in files:
            if f.endswith(".md"):
                rel_path = os.path.relpath(os.path.join(root, f), _skills_dir)
                skills.append(rel_path)

    if not skills:
        return "No skill files found."

    return "Available skills:\n" + "\n".join(f"  - {s}" for s in sorted(skills))


@tool("write_memo", "Working Memory에 메모를 저장합니다. 컨텍스트 압축 후에도 유지됩니다.", is_write=True)
def write_memo(key: str, content: str) -> str:
    """Working Memory에 저장."""
    memory = _get_memory()
    memory.set(key, content)
    return f"OK: Memo '{key}' saved ({len(content)} chars)"


@tool("read_memo", "Working Memory에서 메모를 읽습니다.")
def read_memo(key: str) -> str:
    """Working Memory에서 읽기."""
    memory = _get_memory()
    value = memory.get(key)
    if value is None:
        return f"Memo '{key}' not found. Available keys: {memory.keys()}"
    return f"Memo '{key}':\n{value}"


@tool("list_memos", "Working Memory의 모든 메모 키를 나열합니다.")
def list_memos() -> str:
    """Working Memory 키 목록."""
    memory = _get_memory()
    keys = memory.keys()
    if not keys:
        return "Working Memory is empty."
    return "Working Memory keys:\n" + "\n".join(f"  - {k}" for k in keys)
