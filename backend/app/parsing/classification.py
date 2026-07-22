from pathlib import Path


def classify_chunk(path: Path, chunk: dict) -> dict:
    """Classify one page/table/image block before subtype extraction."""
    suffix = path.suffix.lower()
    text = str(chunk.get("text") or "").lower()
    paired_account_headers = any(
        left in text and right in text
        for left, right in (
            ("付款账号", "收款账号"),
            ("付款方账号", "收款方账号"),
            ("转出账号", "转入账号"),
            ("payer_account", "payee_account"),
        )
    )
    pos_markers = sum(token in text for token in ("商户号", "终端号", "授权码"))
    is_pos_receipt = "pos" in text or pos_markers >= 2
    is_atm_receipt = any(token in text for token in ("atm", "取现", "存现", "自助柜员"))

    if paired_account_headers:
        document_type, record_type = "bank_statement", "bank_transfer"
    elif is_pos_receipt:
        document_type, record_type = "pos_receipt", "card_payment"
    elif is_atm_receipt:
        document_type, record_type = "atm_receipt", "cash_withdrawal"
    elif chunk.get("requires_vision"):
        document_type, record_type = "image_statement", "unknown"
    elif any(token in text for token in ("支付订单", "支付方式", "商家订单号", "支付宝", "微信支付")):
        document_type, record_type = "payment_platform_bill", "payment_order"
    elif any(token in text for token in ("余额", "期初余额", "期末余额", "账户冻结")) and not any(
        token in text for token in ("交易金额", "流水号", "付款账号")
    ):
        document_type, record_type = "account_snapshot", "balance_snapshot"
    elif suffix in {".csv", ".xlsx", ".xls", ".pdf", ".docx"} or any(
        token in text for token in ("交易时间", "交易日期", "借贷", "流水号", "付款账号", "收款账号")
    ):
        document_type, record_type = "bank_statement", "bank_transfer"
    else:
        document_type, record_type = "unknown", "unknown"
    return {
        "document_type": document_type,
        "record_type": record_type,
        "confidence": 0.9 if record_type != "unknown" else 0.2,
    }
