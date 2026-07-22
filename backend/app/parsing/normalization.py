import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ..models import SourceLocation, TransactionRecord


FIELD_ALIASES = {
    "transaction_time": ("交易时间", "交易日期", "记账时间", "发生时间", "完成时间", "支付时间", "时间"),
    "serial_number": ("交易流水号", "流水号", "银行流水号", "交易单号", "订单号", "商户订单号"),
    "payer_account": ("付款账号", "付款账户", "转出账号", "转出账户", "付款方账号"),
    "payer_name": ("付款户名", "付款人", "转出户名", "付款方", "付款方户名"),
    "payer_institution": ("付款机构", "付款方机构", "转出机构", "付款平台"),
    "payer_bank": ("付款行", "付款银行", "转出银行", "付款方银行"),
    "payee_account": ("收款账号", "收款账户", "转入账号", "转入账户", "收款方账号"),
    "payee_name": ("收款户名", "收款人", "转入户名", "收款方", "收款方户名"),
    "payee_institution": ("收款机构", "收款方机构", "转入机构", "收款平台"),
    "payee_bank": ("收款行", "收款银行", "转入银行", "收款方银行"),
    "debit_credit": ("借贷标志", "借贷方向", "收支类型", "方向"),
    "currency": ("币种", "货币"),
    "amount": ("交易金额", "金额", "发生额", "支付金额"),
    "balance_after": ("交易后余额", "余额", "账户余额"),
    "channel": ("交易渠道", "渠道", "支付方式"),
    "summary": ("摘要", "交易摘要", "用途", "备注"),
    "region": ("地区", "交易地区", "发生地"),
    "transaction_type": ("交易类型", "业务类型"),
}


def map_structured_fields(row: dict) -> dict:
    """Map known source columns to the canonical field names without losing raw values."""
    mapped = {field: _lookup(row, field) for field in FIELD_ALIASES}
    if mapped["debit_credit"] in (None, ""):
        if _lookup(row, "amount") == "" and _lookup(row, "debit_credit") == "":
            pass
        income = row.get("收入金额", row.get("贷方金额", ""))
        expense = row.get("支出金额", row.get("借方金额", ""))
        if income not in (None, ""):
            mapped["amount"] = income
            mapped["debit_credit"] = "贷"
        elif expense not in (None, ""):
            mapped["amount"] = expense
            mapped["debit_credit"] = "借"
    return mapped


def _normalized_key(value: object) -> str:
    return re.sub(r"[\s_\-（）()：:]", "", str(value)).lower()


def _lookup(row: dict, field: str, default: object = "") -> object:
    normalized = {_normalized_key(key): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field]:
        key = _normalized_key(alias)
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    return default


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", " ").replace("/", "-")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _parse_amount(value: object) -> float | None:
    if isinstance(value, (int, float, Decimal)):
        return abs(float(value))
    text = re.sub(r"[^0-9.\-()]", "", str(value))
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        amount = float(Decimal(text))
    except (InvalidOperation, ValueError):
        return None
    return abs(amount) if negative or amount < 0 else amount


def normalize_structured_row(row: dict, source: SourceLocation) -> TransactionRecord | None:
    record, _ = normalize_structured_row_with_status(row, source)
    return record


def normalize_structured_row_with_status(
    row: dict, source: SourceLocation
) -> tuple[TransactionRecord | None, str | None]:
    mapped = map_structured_fields(row)
    transaction_time = _parse_datetime(mapped.get("transaction_time"))
    payer_account = str(mapped.get("payer_account") or "").strip()
    payee_account = str(mapped.get("payee_account") or "").strip()
    amount = _parse_amount(mapped.get("amount"))
    if not payer_account or not payee_account:
        return None, "缺少付款账号或收款账号"
    if not transaction_time:
        return None, "缺少或无法解析交易时间"
    if not amount:
        return None, "缺少或无法解析交易金额"
    balance = _parse_amount(_lookup(row, "balance_after"))
    return TransactionRecord(
        transaction_time=transaction_time,
        serial_number=str(mapped.get("serial_number") or "").strip(),
        payer_account=payer_account,
        payer_name=str(mapped.get("payer_name") or "").strip(),
        payer_institution=str(mapped.get("payer_institution") or "").strip(),
        payer_bank=str(mapped.get("payer_bank") or "").strip(),
        payee_account=payee_account,
        payee_name=str(mapped.get("payee_name") or "").strip(),
        payee_institution=str(mapped.get("payee_institution") or "").strip(),
        payee_bank=str(mapped.get("payee_bank") or "").strip(),
        debit_credit=str(mapped.get("debit_credit") or "借").strip() or "借",
        currency=str(mapped.get("currency") or "CNY").strip() or "CNY",
        amount=amount,
        balance_after=balance,
        channel=str(mapped.get("channel") or "").strip(),
        summary=str(mapped.get("summary") or "").strip(),
        region=str(mapped.get("region") or "").strip(),
        transaction_type=str(mapped.get("transaction_type") or "转账").strip() or "转账",
        source=source,
        parser_name="structured",
        confidence={"structured": 1.0},
        review_status="pending",
        provenance="original",
    ), None
