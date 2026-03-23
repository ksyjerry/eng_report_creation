"""
번역 도구 — 전기 DOCX 영문 재사용 원칙.

4-Tier 우선순위:
  Tier 1: 전기 영문 그대로 (exact match) — ~80%
  Tier 2: 전기 영문 기반 최소 조정 — ~10%
  Tier 3: 전기 문체 맞춤 신규 번역 — ~8%
  Tier 4: IFRS 용어 + LLM 번역 — ~2%
"""

from __future__ import annotations

import asyncio
import json
import re
from difflib import SequenceMatcher

from agent.tools import tool


_llm_client = None
_ifrs_terms: dict[str, str] | None = None


def set_llm_client(client) -> None:
    global _llm_client
    _llm_client = client


def _similarity(a: str, b: str) -> float:
    """두 문자열의 유사도 (0~1)."""
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


def _load_ifrs_terms(skills_dir: str) -> dict[str, str]:
    """IFRS 용어집 로드 (캐싱)."""
    global _ifrs_terms
    if _ifrs_terms is not None:
        return _ifrs_terms

    import os
    path = os.path.join(skills_dir, "translation", "ifrs_terms.md")
    terms = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line and "→" not in line and "한국어" not in line and "---" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2:
                        ko, en = parts[0], parts[1]
                        if ko and en and ko != "한국어" and en != "영어":
                            terms[ko] = en
    except Exception:
        pass
    _ifrs_terms = terms
    return terms


def _load_glossary() -> dict[str, str]:
    """WorkingMemory에서 glossary 로드."""
    try:
        from agent.tools.knowledge_tools import _get_memory
        memory = _get_memory()
        glossary_raw = memory.get("glossary") if memory else None
        if glossary_raw:
            glossary = {}
            for line in glossary_raw.split("\n"):
                if " → " in line:
                    parts = line.split(" → ", 1)
                    glossary[parts[0].strip()] = parts[1].strip()
            return glossary
    except Exception:
        pass
    return {}


def _find_best_fuzzy(text: str, candidates: dict[str, str], threshold: float = 0.6) -> tuple[str, str, float] | None:
    """candidates dict에서 text와 가장 유사한 항목 찾기."""
    best_sim = 0.0
    best_pair = None
    for ko, en in candidates.items():
        sim = _similarity(text, ko)
        if sim > best_sim:
            best_sim = sim
            best_pair = (ko, en, sim)
    if best_pair and best_sim >= threshold:
        return best_pair
    return None


def _find_ifrs_match(text: str, ifrs: dict[str, str]) -> str | None:
    """IFRS 용어집에서 exact → partial → fuzzy 순서로 매칭."""
    # exact
    if text in ifrs:
        return ifrs[text]

    # partial: 한국어가 IFRS 용어를 포함하거나 그 반대
    for ko, en in ifrs.items():
        if ko in text or text in ko:
            return en

    # fuzzy: 복합 용어 (sim > 0.7)
    result = _find_best_fuzzy(text, ifrs, threshold=0.7)
    if result:
        return result[1]

    return None


def _translate_date(text: str) -> str | None:
    """한국어 날짜를 영문으로 변환. 변환 불가 시 None."""
    months = {
        "1월": "January", "2월": "February", "3월": "March",
        "4월": "April", "5월": "May", "6월": "June",
        "7월": "July", "8월": "August", "9월": "September",
        "10월": "October", "11월": "November", "12월": "December",
    }
    # "2025년 12월 31일 현재" → "As at December 31, 2025" (longer pattern first)
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*현재", text.strip())
    if m:
        year, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        month_en = months.get(f"{month}월", f"Month{month}")
        return f"As at {month_en} {day}, {year}"

    # "2025년 12월 31일" → "December 31, 2025"
    m = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text.strip())
    if m:
        year, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        month_en = months.get(f"{month}월", f"Month{month}")
        return f"{month_en} {day}, {year}"

    # "제 N 기" 패턴 (번역하지 않음)
    return None


def _extract_json_array(response: str) -> list | None:
    """LLM 응답에서 JSON 배열 추출. 다양한 형식 대응."""
    text = response.strip()

    # 코드블록 제거
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("["):
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue

    # 직접 파싱 시도
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 줄바꿈으로 분리된 응답
    if "\n" in text and not text.startswith("["):
        lines = [l.strip().strip('"').strip("'").rstrip(",") for l in text.split("\n") if l.strip()]
        # 번호 제거: "1. translation" → "translation"
        cleaned = []
        for l in lines:
            m = re.match(r"^\d+\.\s*(.+)", l)
            cleaned.append(m.group(1) if m else l)
        return cleaned

    return None


@tool("translate", "한국어 텍스트를 영어로 번역합니다. 전기 DOCX 영문을 최우선으로 재사용합니다.")
async def translate(
    texts: list,
    prior_translations: dict = None,
    context: str = "",
    style_samples: list = None,
) -> str:
    """
    4-Tier 번역.

    Args:
        texts: 번역할 한국어 텍스트 리스트
        prior_translations: 전기 한→영 매핑 (glossary)
        context: 번역 맥락 (예: "주석 14 유형자산")
        style_samples: 전기 영문 문체 샘플
    """
    prior = dict(prior_translations) if prior_translations else {}

    # prior_translations가 없으면 WorkingMemory glossary에서 자동 로드
    if not prior:
        prior = _load_glossary()

    # IFRS 용어집
    ifrs = _load_ifrs_terms("agent_skills") if _ifrs_terms is None else _ifrs_terms or {}

    results = []
    stats = {"exact": 0, "adjust": 0, "new": 0, "ifrs": 0, "date": 0}

    # LLM 번역이 필요한 항목 모으기
    need_adjust = []  # (index, korean, prior_korean, prior_english, sim)
    need_new = []     # (index, korean)

    for i, text in enumerate(texts):
        text = text.strip()
        if not text:
            results.append((i, text, "", "skip"))
            continue

        # 날짜 변환 체크
        date_en = _translate_date(text)
        if date_en:
            results.append((i, text, date_en, "date"))
            stats["date"] += 1
            continue

        # Tier 1: exact match (glossary)
        if text in prior:
            results.append((i, text, prior[text], "exact"))
            stats["exact"] += 1
            continue

        # Tier 1.5: IFRS exact match
        ifrs_match = _find_ifrs_match(text, ifrs)
        if ifrs_match and _similarity(text, [k for k, v in ifrs.items() if v == ifrs_match][0]) > 0.9:
            results.append((i, text, ifrs_match, "ifrs"))
            stats["ifrs"] += 1
            continue

        # Tier 2: 유사 매칭 (glossary에서 similarity > 0.7)
        fuzzy = _find_best_fuzzy(text, prior, threshold=0.7)
        if fuzzy:
            prior_ko, prior_en, sim = fuzzy
            need_adjust.append((i, text, prior_ko, prior_en, sim))
            continue

        # IFRS partial/fuzzy match
        if ifrs_match:
            results.append((i, text, ifrs_match, "ifrs"))
            stats["ifrs"] += 1
            continue

        # Tier 3/4: 신규 번역
        need_new.append((i, text))

    # Tier 2: LLM으로 조정 (배치 10개, 최대 30개 동시)
    if need_adjust and _llm_client:
        async def _adjust_batch(batch):
            """배치 하나를 LLM으로 조정."""
            try:
                items = [
                    {"current_korean": ko, "prior_korean": pko, "prior_english": pen}
                    for _, ko, pko, pen, _ in batch
                ]
                prompt = (
                    "Adjust these English financial statement translations minimally.\n"
                    "Each item has the prior Korean→English translation and the current Korean text.\n"
                    "The current Korean is slightly different from the prior.\n\n"
                    "RULES:\n"
                    "- Keep the same English style, terminology, and sentence structure\n"
                    "- Only change what is necessary to reflect the Korean difference\n"
                    "- Use IFRS standard English terminology\n"
                    "- Do NOT rephrase or improve the prior English\n\n"
                    f"Items:\n{json.dumps(items, ensure_ascii=False, indent=2)}\n\n"
                    "Return a JSON array of adjusted English strings in the same order."
                )
                response = await _llm_client.complete(
                    system_prompt=(
                        "You are a Korean IFRS financial statement translator. "
                        "You adjust prior-year English translations to match current-year Korean text changes. "
                        "Return ONLY a JSON array of English strings."
                    ),
                    user_prompt=prompt,
                    temperature=0.1,
                    max_tokens=2000,
                )
                translations = _extract_json_array(response)
                if translations and len(translations) >= len(batch):
                    return [(idx, ko, str(en).strip(), "adjust") for (idx, ko, _, _, _), en in zip(batch, translations)]
                raise ValueError("Incomplete response")
            except Exception:
                return [(idx, ko, pen, "adjust-fallback") for idx, ko, _, pen, _ in batch]

        batches = [need_adjust[i:i + 10] for i in range(0, len(need_adjust), 10)]
        sem = asyncio.Semaphore(30)
        async def _limited(batch):
            async with sem:
                return await _adjust_batch(batch)
        batch_results = await asyncio.gather(*[_limited(b) for b in batches])
        for br in batch_results:
            for idx, korean, english, tier in br:
                results.append((idx, korean, english, tier))
                stats["adjust"] += 1
    elif need_adjust:
        for idx, korean, prior_ko, prior_en, sim in need_adjust:
            results.append((idx, korean, prior_en, "adjust-no-llm"))
            stats["adjust"] += 1

    # Tier 3/4: LLM으로 신규 번역 (배치 10개, 최대 30개 동시)
    if need_new and _llm_client:
        style_text = ""
        if style_samples:
            style_text = (
                "Style reference — use the same tone, terminology, and phrasing:\n"
                + "\n".join(f"  - {s}" for s in style_samples[:8])
            )

        glossary_text = ""
        if prior:
            relevant = {}
            for ko, en in prior.items():
                for _, text in need_new:
                    if any(c in ko for c in text[:4]) or _similarity(text, ko) > 0.3:
                        relevant[ko] = en
                        break
            sample = list(relevant.items())[:30] or list(prior.items())[:20]
            glossary_text = (
                "Confirmed terminology from the same document:\n"
                + "\n".join(f"  - {k} → {v}" for k, v in sample)
            )

        context_text = f"Section: {context}" if context else ""

        async def _translate_batch(batch):
            """배치 하나를 LLM으로 신규 번역."""
            texts_to_translate = [text for _, text in batch]
            prompt = (
                "Translate these Korean IFRS financial statement texts to English.\n\n"
                f"{context_text}\n{style_text}\n{glossary_text}\n\n"
                "RULES:\n"
                "- Use formal IFRS English standard terminology\n"
                "- Match the style of the reference translations above\n"
                "- Be consistent: same Korean term → same English term throughout\n"
                "- Do NOT add explanations — return only translations\n"
                "- Preserve parenthetical notes like (*) or (주1)\n\n"
                f"Texts to translate ({len(texts_to_translate)} items):\n"
                f"{json.dumps(texts_to_translate, ensure_ascii=False)}\n\n"
                "Return a JSON array of English translations in the same order."
            )
            try:
                response = await _llm_client.complete(
                    system_prompt=(
                        "You are a Korean IFRS financial statement translator specializing in audit reports. "
                        "Return ONLY a JSON array of English translations."
                    ),
                    user_prompt=prompt,
                    temperature=0.1,
                    max_tokens=3000,
                )
                translations = _extract_json_array(response)
                if translations and len(translations) >= len(batch):
                    return [(idx, ko, str(en).strip(), "new") for (idx, ko), en in zip(batch, translations)]
                raise ValueError("Incomplete JSON response")
            except Exception:
                out = []
                for idx, korean in batch:
                    ifrs_en = _find_ifrs_match(korean, ifrs)
                    if ifrs_en:
                        out.append((idx, korean, ifrs_en, "ifrs-fallback"))
                    else:
                        out.append((idx, korean, f"[UNTRANSLATED] {korean}", "error"))
                return out

        batches = [need_new[i:i + 10] for i in range(0, len(need_new), 10)]
        sem = asyncio.Semaphore(30)
        async def _limited(batch):
            async with sem:
                return await _translate_batch(batch)
        batch_results = await asyncio.gather(*[_limited(b) for b in batches])
        for br in batch_results:
            for idx, korean, english, tier in br:
                results.append((idx, korean, english, tier))
                if tier in ("new",):
                    stats["new"] += 1
                elif tier == "ifrs-fallback":
                    stats["ifrs"] += 1
                else:
                    stats["new"] += 1
    elif need_new:
        for idx, korean in need_new:
            ifrs_en = _find_ifrs_match(korean, ifrs)
            if ifrs_en:
                results.append((idx, korean, ifrs_en, "ifrs-partial"))
                stats["ifrs"] += 1
            else:
                results.append((idx, korean, f"[UNTRANSLATED] {korean}", "no-llm"))
                stats["new"] += 1

    # 인덱스 순으로 정렬
    results.sort(key=lambda x: x[0])

    # 결과 포맷
    lines = ["== Translation Results =="]
    for idx, korean, english, tier in results:
        tag = {"exact": "REUSE", "adjust": "ADJUST", "new": "NEW",
               "ifrs": "IFRS", "date": "DATE", "skip": "SKIP"}.get(tier, tier.upper())
        lines.append(f'{idx+1}. "{korean}" → "{english}" [{tag}]')

    total = sum(stats.values())
    lines.append(f"\nStats: {total} total — exact:{stats['exact']}, adjust:{stats['adjust']}, "
                 f"new:{stats['new']}, ifrs:{stats['ifrs']}, date:{stats['date']}")

    return "\n".join(lines)


@tool("find_prior_translation", "DSD 한국어 텍스트에 대응하는 전기 DOCX 영문을 찾습니다.")
def find_prior_translation(korean_text: str, search_scope: str = "all") -> str:
    """
    DSD 한국어 텍스트가 DOCX에서 어떤 영문으로 쓰였는지 찾기.

    1. Working Memory의 glossary에서 exact/fuzzy 매칭
    2. IFRS 용어집에서 매칭
    """
    text = korean_text.strip()
    if not text:
        return "ERROR: 빈 텍스트"

    # 날짜 변환
    date_en = _translate_date(text)
    if date_en:
        return f'== Prior Translation Found ==\nKorean: "{text}"\nEnglish: "{date_en}"\nSource: date conversion'

    # 1. Glossary에서 검색
    glossary = _load_glossary()
    if glossary:
        # exact match
        if text in glossary:
            return f'== Prior Translation Found ==\nKorean: "{text}"\nEnglish: "{glossary[text]}"\nSource: glossary (exact)'

        # fuzzy match
        fuzzy = _find_best_fuzzy(text, glossary, threshold=0.6)
        if fuzzy:
            ko, en, sim = fuzzy
            return (f'== Prior Translation Found ==\n'
                    f'Korean: "{text}"\n'
                    f'Similar Korean: "{ko}" (sim={sim:.2f})\n'
                    f'English: "{en}"\n'
                    f'Source: glossary (fuzzy)')

    # 2. IFRS 용어집
    ifrs = _load_ifrs_terms("agent_skills") if _ifrs_terms is None else _ifrs_terms or {}
    ifrs_match = _find_ifrs_match(text, ifrs)
    if ifrs_match:
        return f'== Prior Translation Found ==\nKorean: "{text}"\nEnglish: "{ifrs_match}"\nSource: IFRS terms'

    return f'== Prior Translation Not Found ==\nKorean: "{text}"\nNo match in glossary or IFRS terms. Use translate tool with LLM.'


@tool("build_translation_glossary", "DSD-DOCX 매칭 결과로부터 한→영 glossary를 자동 구축합니다.")
def build_translation_glossary(docx_table_index: int, row_pairs: dict) -> str:
    """
    매칭된 행 쌍에서 한→영 대응 추출.

    row_pairs: {"dsd_label": "docx_row_index", ...}
    → DOCX 해당 행의 첫 열 텍스트를 영문으로 사용
    """
    from agent.tools.read_tools import _get_ctx
    from agent.tools.docx_ops.xml_helpers import get_cell_text, findall_w

    ctx = _get_ctx()
    tbl = ctx.get_table(docx_table_index)
    rows = findall_w(tbl, "w:tr")

    glossary = {}
    for ko_label, docx_row_str in row_pairs.items():
        docx_row = int(docx_row_str)
        if 0 <= docx_row < len(rows):
            cells = findall_w(rows[docx_row], "w:tc")
            if cells:
                en_label = get_cell_text(cells[0]).strip()
                if en_label and ko_label:
                    glossary[ko_label] = en_label

    lines = [f"== Glossary Built ==", f"Extracted {len(glossary)} pairs:"]
    for ko, en in glossary.items():
        lines.append(f'  "{ko}" → "{en}"')

    return "\n".join(lines)
