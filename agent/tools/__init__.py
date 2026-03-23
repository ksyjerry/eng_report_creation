"""ToolRegistry — Agent가 사용하는 모든 Tool을 등록, 실행, 로깅하는 중앙 레지스트리."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDef:
    """도구 정의."""
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable
    is_write: bool = False


class ToolRegistry:
    """도구 등록 및 실행."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}
        self._log: list[dict] = []

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        is_write: bool = False,
    ) -> None:
        self._tools[name] = ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
            is_write=is_write,
        )

    async def execute(self, name: str, args: dict) -> str:
        """도구 실행. 결과는 항상 문자열로 반환."""
        if name not in self._tools:
            return f"ERROR: Unknown tool '{name}'. Available: {list(self._tools.keys())}"

        tool = self._tools[name]
        try:
            # LLM이 보낸 인자의 타입을 파라미터 스키마에 맞게 변환
            coerced = _coerce_args(args, tool.parameters)

            if inspect.iscoroutinefunction(tool.func):
                result = await tool.func(**coerced)
            else:
                result = tool.func(**coerced)

            self._log.append({
                "tool": name,
                "args": args,
                "result": str(result)[:500],
                "success": True,
            })
            return str(result)

        except Exception as e:
            error_msg = f"ERROR: {name}() failed — {type(e).__name__}: {e}"
            self._log.append({
                "tool": name,
                "args": args,
                "result": error_msg,
                "success": False,
            })
            return error_msg

    def get_tool(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def to_prompt_text(self) -> str:
        """System Prompt에 삽입할 도구 목록 텍스트."""
        lines = ["## 사용 가능한 도구\n"]
        for tool in self._tools.values():
            lines.append(f"### {tool.name}")
            lines.append(f"{tool.description}\n")
            lines.append(f"Parameters: {json.dumps(tool.parameters, ensure_ascii=False, indent=2)}\n")
        return "\n".join(lines)

    @property
    def log(self) -> list[dict]:
        return self._log


def tool(name: str, description: str, is_write: bool = False):
    """도구 등록 데코레이터. 함수 시그니처에서 파라미터 스키마를 자동 생성."""
    def decorator(func):
        sig = inspect.signature(func)
        # get_type_hints로 실제 타입 객체를 resolve (from __future__ import annotations 대응)
        try:
            import typing
            hints = typing.get_type_hints(func)
        except Exception:
            hints = {}
        params = {}
        type_map = {
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            str: "string",
        }
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "ctx"):
                continue
            annotation = hints.get(param_name, param.annotation)
            param_type = type_map.get(annotation, "string")
            param_info: dict[str, Any] = {"type": param_type}
            if param.default is not inspect.Parameter.empty:
                param_info["default"] = param.default
            params[param_name] = param_info

        func._tool_def = {
            "name": name,
            "description": description,
            "parameters": params,
            "is_write": is_write,
        }
        return func
    return decorator


def _coerce_args(args: dict, param_schema: dict) -> dict:
    """LLM 인자 타입을 파라미터 스키마에 맞게 변환."""
    coerced = {}
    for key, val in args.items():
        spec = param_schema.get(key)
        if spec and val is not None:
            expected = spec.get("type")
            try:
                if expected == "integer" and not isinstance(val, int):
                    val = int(val)
                elif expected == "number" and not isinstance(val, (int, float)):
                    val = float(val)
                elif expected == "boolean" and not isinstance(val, bool):
                    val = str(val).lower() in ("true", "1", "yes")
                elif expected == "string" and not isinstance(val, str):
                    val = str(val)
            except (ValueError, TypeError):
                pass
        coerced[key] = val
    return coerced


def collect_tools(modules: list, registry: ToolRegistry | None = None) -> ToolRegistry:
    """여러 모듈에서 @tool 데코레이터가 붙은 함수를 자동 수집."""
    if registry is None:
        registry = ToolRegistry()
    for module in modules:
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if callable(obj) and hasattr(obj, "_tool_def"):
                td = obj._tool_def
                registry.register(
                    name=td["name"],
                    description=td["description"],
                    parameters=td["parameters"],
                    func=obj,
                    is_write=td["is_write"],
                )
    return registry
