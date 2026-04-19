"""Claude Code headless 出力の厳格JSONスキーマ検証（Layer6）。

Claudeはプロンプトで「最後のassistantメッセージにJSON 1つだけ」を要求する。
stream-json形式のstdoutから最終メッセージを抽出し、schema validationする。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import jsonschema


JOB_POSTING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["is_job", "formatted_message", "fields"],
    "additionalProperties": False,
    "properties": {
        "is_job": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "formatted_message": {"type": "string", "minLength": 100, "maxLength": 1000},
        "fields": {
            "type": "object",
            "required": [
                "title",
                "work_type",
                "hourly_rate",
                "monthly_hours",
                "remote_policy",
                "must_skills",
                "start_date",
                "application_cta",
            ],
            "properties": {
                "title": {"type": "string"},
                "work_type": {"type": "string"},
                "hourly_rate": {"type": "string"},
                "monthly_hours": {"type": "string"},
                "remote_policy": {"type": "string"},
                "must_skills": {"type": "array", "items": {"type": "string"}},
                "welcome_skills": {"type": "array", "items": {"type": "string"}},
                "start_date": {"type": "string"},
                "application_cta": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "conflicts": {"type": "array", "items": {"type": "string"}},
    },
}

CANDIDATE_REPLY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["intent", "confidence", "reply_text", "scope_ok"],
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reply_text": {"type": "string", "minLength": 1, "maxLength": 500},
        "scope_ok": {"type": "boolean"},
        "escalation_reason": {"type": "string"},
    },
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    parsed: Any | None = None
    error: str = ""


def extract_last_json(stream_json_stdout: str) -> str | None:
    """stream-json 出力から最後の assistant テキスト → 中のJSONを抽出。

    Claude Code の stream-json は1行1JSONオブジェクト。最後の `assistant` roleの
    `content[].text` に期待する最終JSONが入っている前提。
    """
    last_text: str | None = None
    for line in stream_json_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "assistant":
            msg = obj.get("message") or {}
            contents = msg.get("content") or []
            for c in contents:
                if isinstance(c, dict) and c.get("type") == "text":
                    last_text = c.get("text")

    if last_text is None:
        return None

    # テキスト内から最後のJSONブロックを抽出
    # ```json ... ``` 形式または素のJSONに対応
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", last_text, re.DOTALL)
    if m:
        return m.group(1)
    # 素のJSONとして全文試す
    return last_text.strip()


def validate_output(raw_json_text: str, schema: dict[str, Any]) -> ValidationResult:
    try:
        parsed = json.loads(raw_json_text)
    except json.JSONDecodeError as e:
        return ValidationResult(False, error=f"json_parse_error:{e}")

    try:
        jsonschema.validate(parsed, schema)
    except jsonschema.ValidationError as e:
        return ValidationResult(False, error=f"schema_violation:{e.message}")

    return ValidationResult(True, parsed=parsed)
