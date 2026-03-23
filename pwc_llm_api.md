# PwC GenAI Gateway (LLM) 사용 스킬

## 개요

PwC 내부 GenAI Gateway를 통해 LLM을 호출하는 방법. Anthropic Claude, Google Gemini 등 다양한 모델을 동일한 API 인터페이스로 사용할 수 있다.

---

## 1. 엔드포인트 정보

| 항목 | 값 |
|------|-----|
| **Base URL** | `https://genai-sharedservice-americas.pwcinternal.com` |
| **API Path** | `/v1/responses` |
| **Auth** | `Authorization: Bearer {API_KEY}` |
| **Content-Type** | `application/json` |

---

## 2. 사용 가능한 모델

| 모델 ID | 설명 |
|---------|------|
| `bedrock.anthropic.claude-sonnet-4-6` | Claude Sonnet 4.6 (AWS Bedrock 경유) |
| `vertex_ai.gemini-3.1-pro-preview` | Gemini 3.1 Pro Preview (Google Vertex AI 경유) |

모델 ID 패턴: `{provider}.{model_name}`
- `bedrock.` 접두사 → AWS Bedrock 경유
- `vertex_ai.` 접두사 → Google Vertex AI 경유

---

## 3. 환경 변수 (.env)

```env
GENAI_BASE_URL=https://genai-sharedservice-americas.pwcinternal.com
PwC_LLM_API_KEY=your-api-key-here
PwC_LLM_MODEL=bedrock.anthropic.claude-sonnet-4-6
```

### pydantic-settings 설정 예시

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GENAI_BASE_URL: str = "https://genai-sharedservice-americas.pwcinternal.com"
    GENAI_API_KEY: str = Field(default="", validation_alias="PwC_LLM_API_KEY")
    GENAI_MODEL: str = Field(
        default="bedrock.anthropic.claude-sonnet-4-6",
        validation_alias="PwC_LLM_MODEL",
    )
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```

---

## 4. 요청 형식 (Responses API)

```python
POST {base_url}/v1/responses

{
    "model": "bedrock.anthropic.claude-sonnet-4-6",
    "input": [
        {"role": "system", "content": "시스템 프롬프트"},
        {"role": "user", "content": "사용자 메시지"}
    ],
    "temperature": 0.1,
    "max_tokens": 4096
}
```

### 주요 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `model` | string | 필수 | 모델 ID (예: `bedrock.anthropic.claude-sonnet-4-6`) |
| `input` | array | 필수 | 메시지 배열 (`role` + `content`) |
| `temperature` | float | 0.1 | 0.0~1.0, 낮을수록 결정적 |
| `max_tokens` | int | 4096 | 최대 출력 토큰 수 |

### input 메시지 role

| role | 용도 |
|------|------|
| `system` | 시스템 프롬프트 (행동 규칙, 페르소나 설정) |
| `user` | 사용자 입력 (질문, 데이터) |

---

## 5. 응답 형식

Gateway는 모델에 따라 두 가지 응답 형식을 반환할 수 있다.

### 형식 A: Responses API (주 형식)

```json
{
    "output": [
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "응답 텍스트"
                }
            ]
        }
    ]
}
```

텍스트 추출: `data["output"][0]["content"][0]["text"]`

### 형식 B: Chat Completions API (대체 형식)

```json
{
    "choices": [
        {
            "message": {
                "content": "응답 텍스트"
            }
        }
    ]
}
```

텍스트 추출: `data["choices"][0]["message"]["content"]`

### 안전한 응답 파싱 (두 형식 모두 처리)

```python
data = response.json()

# Format 1: Responses API
if "output" in data:
    for item in data["output"]:
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    return block["text"]
            for block in item.get("content", []):
                if "text" in block:
                    return block["text"]

# Format 2: Chat Completions API
if "choices" in data:
    return data["choices"][0]["message"]["content"]
```

---

## 6. Python 비동기 클라이언트 구현 (전체 코드)

```python
"""PwC GenAI Gateway async client."""

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class GenAIClient:
    """Async client for PwC Internal GenAI Gateway."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=timeout)

    # ── 기본 호출 ──

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """LLM 호출 + 자동 재시도 (3회, exponential backoff)."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await self.client.post(
                    f"{self.base_url}/v1/responses",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json={
                        "model": self.model,
                        "input": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Responses API format
                try:
                    text = data["output"][0]["content"][0]["text"]
                except (KeyError, IndexError):
                    # Fallback: Chat Completions format
                    text = data["choices"][0]["message"]["content"]

                if not text or not text.strip():
                    raise ValueError("Empty response from GenAI Gateway")

                return text

            except (httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError) as e:
                last_error = e
                logger.warning(
                    "GenAI attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, e
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

        raise RuntimeError(
            f"GenAI request failed after {MAX_RETRIES} attempts: {last_error}"
        )

    # ── JSON 응답 호출 ──

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """JSON 응답 요청 + 자동 파싱. JSON 파싱 실패 시 3회 재시도."""
        for json_attempt in range(3):
            raw = await self.complete(
                system_prompt=(
                    system_prompt
                    + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
                    "Do NOT include any explanation or markdown formatting. "
                    "Output must start with { and end with }."
                ),
                user_prompt=user_prompt,
                **kwargs,
            )
            cleaned = _extract_json(raw)

            if not cleaned:
                logger.warning("JSON attempt %d/3: no JSON found", json_attempt + 1)
                if json_attempt < 2:
                    await asyncio.sleep(2 * (json_attempt + 1))
                    continue
                raise json.JSONDecodeError("No JSON object found", raw, 0)

            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                if json_attempt < 2:
                    logger.warning("JSON parse failed (attempt %d/3)", json_attempt + 1)
                    await asyncio.sleep(2 * (json_attempt + 1))
                else:
                    raise

    async def close(self) -> None:
        await self.client.aclose()


def _extract_json(raw: str) -> str:
    """LLM 응답에서 JSON 객체 추출.

    처리하는 형식:
    - 순수 JSON: {"key": ...}
    - 코드 펜스: ```json\n{...}\n```
    - 전후 텍스트: "Here is the result:\n{...}\nHope this helps"
    - 중첩 중괄호
    """
    import re

    text = raw.strip()

    # 1. ```json ... ``` 코드 펜스 제거
    if "```" in text:
        fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if fence_match:
            text = fence_match.group(1).strip()

    # 2. 이미 {로 시작하면 바로 반환
    if text.startswith("{"):
        return text

    # 3. 첫 번째 {를 찾아 대응하는 } 매칭
    first_brace = text.find("{")
    if first_brace < 0:
        return ""

    depth = 0
    in_string = False
    escape_next = False
    for i in range(first_brace, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            if in_string:
                escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[first_brace : i + 1]

    return text[first_brace:]
```

---

## 7. 사용 예시

### 기본 텍스트 호출

```python
client = GenAIClient(
    base_url="https://genai-sharedservice-americas.pwcinternal.com",
    api_key="your-key",
    model="bedrock.anthropic.claude-sonnet-4-6",
)

result = await client.complete(
    system_prompt="You are a helpful assistant.",
    user_prompt="What is K-IFRS?",
    temperature=0.1,
    max_tokens=2048,
)
print(result)
```

### JSON 응답 호출

```python
data = await client.complete_json(
    system_prompt="Respond in JSON with keys: summary, items",
    user_prompt="Summarize the following financial data: ...",
    temperature=0.1,
    max_tokens=4096,
)
print(data["summary"])
print(data["items"])
```

### FastAPI 통합

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.close()  # 앱 종료 시 HTTP 클라이언트 정리

app = FastAPI(lifespan=lifespan)

@app.post("/api/ask")
async def ask(question: str):
    answer = await client.complete(
        system_prompt="You are a financial expert.",
        user_prompt=question,
    )
    return {"answer": answer}
```

---

## 8. 권장 사항

### temperature 설정

| 용도 | temperature | 이유 |
|------|-------------|------|
| 재무제표 번역/편집 | 0.1 | 정확성 최우선, 일관된 출력 |
| 데이터 분석/요약 | 0.2~0.3 | 약간의 다양성 허용 |
| 창작/브레인스토밍 | 0.7~0.9 | 다양한 아이디어 생성 |

### max_tokens 설정

| 용도 | max_tokens | 비고 |
|------|-----------|------|
| 짧은 응답 (분류, 판단) | 1024 | |
| 일반 텍스트 응답 | 4096 | 기본값 |
| 긴 JSON (표 편집 전략) | 8192~16384 | 복잡한 표 데이터 포함 시 |

### 에러 처리

- **3회 자동 재시도** + exponential backoff (2초, 4초, 6초)
- `httpx.HTTPStatusError` — 4xx/5xx HTTP 에러
- `httpx.RequestError` — 네트워크 오류, 타임아웃
- `KeyError` — 예상치 못한 응답 형식
- `ValueError` — 빈 응답

### 타임아웃

- 기본: `120초` (간단한 질의)
- 복잡한 작업: `180초` (긴 문서 번역, 대량 데이터 분석)
- `httpx.AsyncClient(timeout=120.0)` 으로 설정

### 동시성 제어

```python
import asyncio

semaphore = asyncio.Semaphore(10)  # 최대 10개 동시 호출

async def rate_limited_call(prompt):
    async with semaphore:
        return await client.complete(
            system_prompt="...",
            user_prompt=prompt,
        )

# 여러 호출을 병렬로 실행
results = await asyncio.gather(*[
    rate_limited_call(p) for p in prompts
])
```

---

## 9. cURL 테스트

```bash
curl -X POST https://genai-sharedservice-americas.pwcinternal.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "bedrock.anthropic.claude-sonnet-4-6",
    "input": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello, what is K-IFRS?"}
    ],
    "temperature": 0.1,
    "max_tokens": 1024
  }'
```

---

## 10. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 401 Unauthorized | API 키 만료/잘못됨 | `.env`의 `PwC_LLM_API_KEY` 확인 |
| 429 Too Many Requests | Rate limit 초과 | `asyncio.Semaphore`로 동시성 제한 |
| 504 Gateway Timeout | 요청이 너무 김 | `max_tokens` 줄이거나 프롬프트 분할 |
| 빈 응답 | 모델 출력 길이 초과 | `max_tokens` 증가 |
| JSON 파싱 실패 | LLM이 마크다운 포함 | `_extract_json()` 사용하여 코드 펜스 자동 제거 |
| 알 수 없는 응답 형식 | 모델별 형식 차이 | Responses API + Chat Completions 양쪽 모두 시도 |
