from __future__ import annotations

import json

_TYPE_LABELS = {
    "bank_transfer": "银行转账/借贷流水",
    "payment_order": "第三方支付订单",
    "card_payment": "POS消费",
    "cash_withdrawal": "ATM取现",
    "cash_deposit": "现金存入",
    "refund": "退款",
    "reversal": "冲正/撤销",
    "settlement": "商户清算",
    "balance_snapshot": "余额快照",
    "unknown": "未知资金材料",
}


def build_classification_prompt(text: str = "") -> str:
    return (
        "判断这段资金材料最符合的业务记录类型，只输出一个 JSON 对象。"
        "可选类型：bank_transfer、payment_order、card_payment、cash_withdrawal、"
        "cash_deposit、refund、reversal、settlement、balance_snapshot、unknown。"
        "依据可见文字，不确定时选择 unknown，不要提取或补造交易。\n"
        f"材料片段：{text[:12000]}"
    )


def build_extraction_prompt(record_type: str = "bank_transfer", schema: dict | None = None) -> str:
    label = _TYPE_LABELS.get(record_type, _TYPE_LABELS["unknown"])
    contract = json.dumps(
        schema or {"transactions": "按服务端提供的严格 Schema 输出"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""将材料中的{label}逐笔转换为标准交易数组。

<固定规则>
- 只输出材料明确可见的事实；无法确认的字段填 null，不得猜测。
- POS、ATM、现金端点可能没有银行卡号；账号必须填 null，保留 merchant_id、terminal_id 或渠道信息。
- 每笔记录独立输出，不合并、不汇总；失败、待处理、撤销、退款保留 event_status 和 relation_type。
- 金额为正数，方向放在 debit_credit；原始流水号、摘要和证据文字尽量照抄。
- 严格只输出 Schema 白名单字段，不要输出解释、Markdown 或其他键。
- 不得虚构银行卡号、户名、机构或余额。
</固定规则>

<类型提示>
当前类型：{record_type}。如果材料实际属于其他类型，仍按可见事实提取，并将不确定字段置 null。
</类型提示>

JSON Schema：
{contract}
"""


def build_validation_retry_prompt(errors: str) -> str:
    return (
        "上一次输出未通过后端 JSON/Pydantic 校验。请只修正以下字段级错误，重新输出完整交易数组，"
        "仍须严格遵守原 Schema；不要编造缺失事实。\n校验失败：" + errors
    )
