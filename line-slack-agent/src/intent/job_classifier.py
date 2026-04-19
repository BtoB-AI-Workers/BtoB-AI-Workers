"""Phase 1案件投稿専用L2判定（Haiku SDK直叩き）。

入力（Slackメンションテキスト）が「案件情報として整形可能か」を二値判定。
出力: {is_job, confidence, missing_fields, conflicts}

config/intent_taxonomy.yaml の `job_posting` セクションで閾値管理。
Phase 1ゲート: precision=1.0（fp=0）, recall≥0.9 を tests/fixtures/job_posting_eval/ で満たす。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from anthropic import Anthropic


@dataclass(frozen=True)
class JobClassification:
    is_job: bool
    confidence: float
    missing_fields: list[str]
    conflicts: list[str]
    raw_response: str


SYSTEM_PROMPT = """You are a strict classifier for a job posting automation system.

Your task: given Japanese text that may be a job posting request, decide whether it contains sufficient information to be formatted into a structured job posting for posting to an external LINE group.

Required fields (must be extractable or clearly implied):
- title (role name)
- work_type (SES / 架電 / 事務 / etc)
- hourly_rate (e.g., 1500-2000円)
- monthly_hours (e.g., 月80時間)
- remote_policy (フルリモート / 一部出社 / フル出社)
- must_skills (at least one)
- start_date (即日 / 来月 / 具体日付など)
- application_cta (応募方法の言及があるか)

Output a single JSON object, no prose:
{
  "is_job": bool,
  "confidence": float (0.0-1.0),
  "missing_fields": [string],
  "conflicts": [string]
}

Rules:
- If the text is a non-job message (greeting, memo, unrelated chat), is_job=false, confidence=高.
- If it is partially a job but missing required fields, is_job=false (do not format incomplete postings).
- Only is_job=true when all required fields are present AND there are no conflicts.
- Be strict: false positives cause production posting errors. Prefer false over ambiguous.
"""


def classify(
    text: str,
    *,
    model: str = "claude-haiku-4-5-20251001",
    api_key: str | None = None,
) -> JobClassification:
    client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    raw = resp.content[0].text if resp.content else "{}"
    try:
        parsed = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        return JobClassification(
            is_job=False,
            confidence=0.0,
            missing_fields=["parse_error"],
            conflicts=[],
            raw_response=raw,
        )
    return JobClassification(
        is_job=bool(parsed.get("is_job", False)),
        confidence=float(parsed.get("confidence", 0.0)),
        missing_fields=list(parsed.get("missing_fields", [])),
        conflicts=list(parsed.get("conflicts", [])),
        raw_response=raw,
    )


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # ```json\n...\n``` or ```\n...\n```
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return text


def load_thresholds(config_path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    return (data.get("job_posting") or {}).get("thresholds") or {"min_confidence": 0.85}


def passes_threshold(result: JobClassification, thresholds: dict[str, Any]) -> bool:
    min_conf = float(thresholds.get("min_confidence", 0.85))
    return (
        result.is_job
        and result.confidence >= min_conf
        and not result.missing_fields
        and not result.conflicts
    )
