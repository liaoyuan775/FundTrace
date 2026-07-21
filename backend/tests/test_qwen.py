import json

import httpx

from app.config import Settings
from app.ai.qwen import QwenAdapter, transaction_response_format


def test_qwen_uses_strict_fixed_transaction_schema():
    response_format = transaction_response_format()

    assert response_format["type"] == "json_schema"
    definition = response_format["json_schema"]
    assert definition["name"] == "fundtrace_transactions"
    assert definition["strict"] is True
    transaction_schema = definition["schema"]["$defs"]["ExtractedTransaction"]
    assert transaction_schema["additionalProperties"] is False
    assert set(transaction_schema["required"]) == {
        "transaction_time", "serial_number", "payer_account", "payer_name", "payer_institution", "payer_bank",
        "payee_account", "payee_name", "payee_institution", "payee_bank", "debit_credit", "currency", "amount",
        "balance_after", "channel", "summary", "region", "transaction_type",
    }


def test_qwen_fallback_keeps_fixed_contract_and_marks_actual_mode(monkeypatch):
    calls = []
    transaction = {
        "transaction_time": "2026-07-17T10:00:00",
        "serial_number": "T001",
        "payer_account": "62220001",
        "payer_name": "甲",
        "payer_institution": "",
        "payer_bank": "甲银行",
        "payee_account": "62220002",
        "payee_name": "乙",
        "payee_institution": "",
        "payee_bank": "乙银行",
        "debit_credit": "借",
        "currency": "CNY",
        "amount": 100,
        "balance_after": None,
        "channel": "手机银行",
        "summary": "转账",
        "region": "湖南长沙",
        "transaction_type": "转账",
    }

    def fake_post(url, **kwargs):
        calls.append(json.loads(json.dumps(kwargs["json"])))
        request = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(400, request=request, json={"error": "unsupported"})
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": json.dumps({"transactions": [transaction]})}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = QwenAdapter(Settings(qwen_base_url="http://model.test/v1", qwen_api_key="secret"))

    records = adapter.normalize("一笔流水")

    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[1]["response_format"] == {"type": "json_object"}
    assert "payer_account" in calls[1]["messages"][0]["content"]
    assert records[0].prompt_version == "v2-json-object"
    assert "已降级" in adapter.last_warning
