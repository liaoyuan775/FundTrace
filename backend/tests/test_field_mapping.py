from app.models import SourceLocation
from app.parsing.normalization import map_structured_fields, normalize_structured_row_with_status


def test_field_mapping_maps_common_bank_aliases_and_direction_columns():
    mapped = map_structured_fields({
        "发生时间": "2026-07-21 10:30:00",
        "转出账户": "6212 0000 0000 0002",
        "转出户名": "张某",
        "转入账户": "6228-0000-0000-0001",
        "转入户名": "李某",
        "支出金额": "10,000.00",
        "备注": "转账",
    })
    assert mapped["transaction_time"] == "2026-07-21 10:30:00"
    assert mapped["payer_account"] == "6212 0000 0000 0002"
    assert mapped["amount"] == "10,000.00"
    assert mapped["debit_credit"] == "借"


def test_structured_row_returns_reason_instead_of_silent_drop():
    record, reason = normalize_structured_row_with_status(
        {"交易日期": "2026-07-21", "金额": "100"},
        SourceLocation(source_file_id="FILE-1", row_number=4),
    )
    assert record is None
    assert reason == "缺少付款账号或收款账号"
