import json
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.config import Settings
from app.ai.qwen import QwenAdapter, classification_response_format, transaction_response_format
from app.ai.prompts.financial_events import build_extraction_prompt


def test_qwen_uses_strict_fixed_transaction_schema():
    response_format = transaction_response_format()

    assert response_format["type"] == "json_schema"
    definition = response_format["json_schema"]
    assert definition["name"] == "fundtrace_transactions"
    assert definition["strict"] is True
    transaction_schema = definition["schema"]["$defs"]["ExtractedTransaction"]
    assert transaction_schema["additionalProperties"] is False
    assert {
        "transaction_time", "serial_number", "payer_account", "payer_name", "payer_institution", "payer_bank",
        "payee_account", "payee_name", "payee_institution", "payee_bank", "debit_credit", "currency", "amount",
        "balance_after", "channel", "summary", "region", "transaction_type",
    }.issubset(transaction_schema["required"])


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
        "event_status": "success",
        "order_id": None,
        "batch_id": None,
        "merchant_id": None,
        "merchant_name": None,
        "terminal_id": None,
        "authorization_code": None,
        "fee": None,
        "related_transaction_id": None,
        "relation_type": None,
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


def test_subtype_prompt_selects_pos_specific_evidence_fields():
    prompt = build_extraction_prompt("card_payment")

    assert "POS消费" in prompt
    assert "merchant_id" in prompt
    assert "terminal_id" in prompt
    assert "不得虚构银行卡号" in prompt


def test_qwen_classifier_uses_strict_business_type_schema(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps({
                "document_type": "pos_receipt",
                "record_type": "card_payment",
                "confidence": 0.98,
            })}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = QwenAdapter(Settings(qwen_base_url="http://model.test/v1", qwen_api_key="secret"))

    result = adapter.classify("商户号 M001 终端号 P001")

    assert result.record_type == "card_payment"
    assert calls[0]["response_format"] == classification_response_format()


def test_qwen_image_success_updates_shared_capability_across_threads(tmp_path, monkeypatch):
    image_path = tmp_path / "receipt.png"
    image_path.write_bytes(b"png")

    def fake_get(url, **kwargs):
        return httpx.Response(200, request=httpx.Request("GET", url), json={"data": []})

    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps({
                "document_type": "pos_receipt",
                "record_type": "card_payment",
                "confidence": 0.98,
            })}}]},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = QwenAdapter(Settings(qwen_base_url="http://model.test/v1", qwen_api_key="secret"))

    initial = adapter.probe()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(adapter.classify, "POS签购单", image_path).result()
    effective = adapter.probe()

    assert result.record_type == "card_payment"
    assert initial.vision_attempted is False
    assert initial.vision is False
    assert effective.vision_attempted is True
    assert effective.vision is True


def test_qwen_validation_error_is_sent_back_on_retry(monkeypatch):
    calls = []
    invalid = {
        "transactions": [{
            "transaction_time": "not-a-date",
            "serial_number": "T001",
            "payer_account": "1",
            "payer_name": "甲",
            "payer_institution": None,
            "payer_bank": None,
            "payee_account": "2",
            "payee_name": "乙",
            "payee_institution": None,
            "payee_bank": None,
            "debit_credit": "借",
            "currency": "CNY",
            "amount": 100,
            "balance_after": None,
            "channel": "手机银行",
            "summary": None,
            "region": None,
            "transaction_type": "转账",
            "event_status": "success",
            "order_id": None,
            "batch_id": None,
            "merchant_id": None,
            "merchant_name": None,
            "terminal_id": None,
            "authorization_code": None,
            "fee": None,
            "related_transaction_id": None,
            "relation_type": None,
        }]
    }
    valid = json.loads(json.dumps(invalid))
    valid["transactions"][0]["transaction_time"] = "2026-07-17T10:00:00"

    def fake_post(url, **kwargs):
        calls.append(json.loads(json.dumps(kwargs["json"])))
        body = invalid if len(calls) == 1 else valid
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(body)}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = QwenAdapter(Settings(qwen_base_url="http://model.test/v1", qwen_api_key="secret"))

    records = adapter.normalize("一笔流水", record_type="bank_transfer")

    assert len(records) == 1
    assert len(calls) == 2
    retry_content = calls[1]["messages"][-1]["content"]
    assert "transactions.0.transaction_time" in retry_content
    assert "校验失败" in retry_content


def test_pos_record_can_keep_unobserved_accounts_empty(tmp_path, monkeypatch):
    transaction = {
        "transaction_time": "2026-07-17T10:00:00",
        "serial_number": "POS-001",
        "payer_account": None,
        "payer_name": None,
        "payer_institution": None,
        "payer_bank": None,
        "payee_account": None,
        "payee_name": "测试商户",
        "payee_institution": None,
        "payee_bank": None,
        "debit_credit": "借",
        "currency": "CNY",
        "amount": 88,
        "balance_after": None,
        "channel": "POS",
        "summary": None,
        "region": None,
        "transaction_type": "消费",
        "event_status": "success",
        "order_id": None,
        "batch_id": None,
        "merchant_id": "M001",
        "merchant_name": "测试商户",
        "terminal_id": "P001",
        "authorization_code": "A001",
        "fee": None,
        "related_transaction_id": None,
        "relation_type": None,
    }

    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps({"transactions": [transaction]})}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = QwenAdapter(Settings(qwen_base_url="http://model.test/v1", qwen_api_key="secret"))
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"jpg")

    record = adapter.normalize("POS签购单", image_path, record_type="card_payment")[0]

    assert record.payer_account == ""
    assert record.payee_account == ""
    assert record.merchant_id == "M001"
    assert record.terminal_id == "P001"
    assert adapter.vision_attempted is True
    assert adapter.vision_succeeded is True


def test_qwen_defaults_blank_currency_and_keeps_explicit_currency(monkeypatch):
    transaction = {
        "transaction_time": "2026-07-17T10:00:00",
        "serial_number": "T001",
        "payer_account": "1",
        "payer_name": "甲",
        "payer_institution": None,
        "payer_bank": None,
        "payee_account": "2",
        "payee_name": "乙",
        "payee_institution": None,
        "payee_bank": None,
        "debit_credit": "借",
        "currency": None,
        "amount": 100,
        "balance_after": None,
        "channel": "手机银行",
        "summary": None,
        "region": None,
        "transaction_type": "转账",
        "event_status": "success",
        "order_id": None,
        "batch_id": None,
        "merchant_id": None,
        "merchant_name": None,
        "terminal_id": None,
        "authorization_code": None,
        "fee": None,
        "related_transaction_id": None,
        "relation_type": None,
    }

    empty_currency = json.loads(json.dumps(transaction))
    empty_currency["serial_number"] = "T002"
    empty_currency["currency"] = ""
    usd_currency = json.loads(json.dumps(transaction))
    usd_currency["serial_number"] = "T003"
    usd_currency["currency"] = "USD"

    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps({
                "transactions": [transaction, empty_currency, usd_currency],
            })}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = QwenAdapter(Settings(qwen_base_url="http://model.test/v1", qwen_api_key="secret"))

    records = adapter.normalize("一笔流水")

    assert [record.currency for record in records] == ["CNY", "CNY", "USD"]
