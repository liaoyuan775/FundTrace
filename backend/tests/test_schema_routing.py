from pathlib import Path

from app.parsing.classification import classify_chunk


def test_classifier_routes_pos_and_atm_blocks_to_specific_record_types():
    pos = classify_chunk(Path("receipt.png"), {"text": "商户号 123 终端号 456 授权码 789"})
    atm = classify_chunk(Path("receipt.png"), {"text": "ATM 取现 5000"})
    assert pos["record_type"] == "card_payment"
    assert atm["record_type"] == "cash_withdrawal"


def test_classifier_keeps_paired_account_table_as_transfer_with_atm_row_marker():
    result = classify_chunk(
        Path("statement.pdf"),
        {"text": "交易时间 付款账号 收款账号 金额\n10:30 62220001 ATM服务中心 取现 5000"},
    )

    assert result["document_type"] == "bank_statement"
    assert result["record_type"] == "bank_transfer"


def test_classifier_prefers_strong_receipt_markers_over_generic_time_markers():
    pos = classify_chunk(
        Path("receipt.png"),
        {"text": "交易时间 10:30 商户号 M001 终端号 P001 授权码 A001"},
    )
    atm = classify_chunk(
        Path("receipt.jpg"),
        {"text": "交易日期 2026-07-22 ATM 取现 5000 终端编号 T001"},
    )

    assert pos["record_type"] == "card_payment"
    assert atm["record_type"] == "cash_withdrawal"


def test_classifier_routes_unknown_blocks_to_manual_review_type():
    result = classify_chunk(Path("unknown.bin"), {"text": "无法判断的材料"})
    assert result == {
        "document_type": "unknown",
        "record_type": "unknown",
        "confidence": 0.2,
    }
