"""WorkingMemory — Agent 세션 동안 유지되는 Key-Value 메모리."""

from __future__ import annotations


class WorkingMemory:
    """세션 내 Key-Value 메모리. 컨텍스트 압축 후에도 유지."""

    def __init__(self):
        self._store: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def keys(self) -> list[str]:
        return list(self._store.keys())

    def items(self) -> list[tuple[str, str]]:
        return list(self._store.items())

    def to_summary(self) -> str:
        """Working Memory 전체를 텍스트로 직렬화."""
        if not self._store:
            return "(empty)"
        lines = []
        for k, v in self._store.items():
            # 긴 값은 앞 200자만 표시
            display_v = v[:200] + "..." if len(v) > 200 else v
            lines.append(f"- {k}: {display_v}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: str) -> bool:
        return key in self._store
