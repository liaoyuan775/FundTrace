import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).parents[1] / "app" / "parsing" / "schemas" / "financial_event.schema.json"


def test_financial_event_schema_accepts_common_transfer_event():
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    event = {
        "schema_version": "financial_event_v1",
        "record_type": "bank_transfer",
        "event": {
            "event_time": "2026-07-21T10:30:00",
            "amount": 10000,
            "currency": "CNY",
            "direction": "out",
            "source_entity": {
                "entity_type": "personal_account",
                "account": "62120000000000002",
                "masked_account": None,
                "name": "张某",
                "institution": None,
                "bank": "测试银行",
                "resolution": "exact",
            },
            "target_entity": {
                "entity_type": "bank_account",
                "account": "62280000000000001",
                "masked_account": None,
                "name": "李某",
                "institution": None,
                "bank": "测试银行",
                "resolution": "exact",
            },
            "status": "success",
        },
        "evidence": {"source_file_id": "FILE-001", "page_number": 3},
        "extraction": {"method": "structured", "status": "extracted"},
    }
    Draft202012Validator(schema).validate(event)


def test_financial_event_schema_rejects_unknown_top_level_fields():
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    invalid = {
        "schema_version": "financial_event_v1",
        "record_type": "unknown",
        "event": {},
        "evidence": {"source_file_id": "FILE-001"},
        "extraction": {"method": "model", "status": "needs_manual_review"},
        "bank_specific_free_text": "不得进入统一字段",
    }
    with pytest.raises(Exception):
        Draft202012Validator(schema).validate(invalid)
