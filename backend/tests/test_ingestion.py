from datetime import datetime
import json
from concurrent.futures import ThreadPoolExecutor

from docx import Document

from app.ingestion.dedup import canonical_records, group_duplicate_records
from app.models import CaseRecord, SourceLocation, TransactionRecord
from app.parsing.extractors import extract_material
from app.parsing.normalization import normalize_structured_row
from app.repository.file_repo import FileRepository


def record(serial: str, amount: float = 1000, payee: str = "62220002") -> TransactionRecord:
    return TransactionRecord(
        transaction_time=datetime(2026, 7, 17, 10),
        serial_number=serial,
        payer_account="62220001",
        payer_name="测试付款人",
        payer_bank="测试银行",
        payee_account=payee,
        payee_name="测试收款人",
        payee_bank="测试银行",
        amount=amount,
        review_status="confirmed",
    )


def test_structured_row_aliases_normalize_to_transaction_with_source():
    source = SourceLocation(source_file_id="FILE-1", sheet_name="交易明细", row_number=3)
    normalized = normalize_structured_row(
        {
            "交易日期": "2026/07/17 10:08:09",
            "交易流水号": "BANK-A-001",
            "付款账号": "6222 0001",
            "付款户名": "受害人甲",
            "付款机构": "手机银行账户",
            "付款行": "甲银行长沙分行",
            "收款账号": "6222 0002",
            "收款户名": "张某",
            "收款机构": "聚合支付平台",
            "收款行": "乙银行深圳分行",
            "交易金额": "¥12,345.67",
            "交易渠道": "手机银行",
            "摘要": "转账",
            "地区": "湖南长沙",
        },
        source,
    )

    assert normalized is not None
    assert normalized.transaction_time == datetime(2026, 7, 17, 10, 8, 9)
    assert normalized.serial_number == "BANK-A-001"
    assert normalized.payer_account == "62220001"
    assert normalized.payer_institution == "手机银行账户"
    assert normalized.payee_account == "62220002"
    assert normalized.payee_institution == "聚合支付平台"
    assert normalized.amount == 12345.67
    assert normalized.source == source
    assert normalized.parser_name == "structured"


def test_docx_table_is_extracted_as_one_header_aware_chunk(tmp_path):
    path = tmp_path / "statement.docx"
    document = Document()
    table = document.add_table(rows=3, cols=3)
    for column, value in enumerate(("交易时间", "流水号", "金额")):
        table.rows[0].cells[column].text = value
    for column, value in enumerate(("2026-07-17 10:00:00", "T001", "100.00")):
        table.rows[1].cells[column].text = value
    for column, value in enumerate(("2026-07-17 10:05:00", "T002", "200.00")):
        table.rows[2].cells[column].text = value
    document.save(path)

    chunks = extract_material(path)

    assert len(chunks) == 1
    assert chunks[0]["table_number"] == 1
    assert chunks[0]["row_evidence"] == [
        {"row_number": 2, "text": "2026-07-17 10:00:00\tT001\t100.00"},
        {"row_number": 3, "text": "2026-07-17 10:05:00\tT002\t200.00"},
    ]
    assert chunks[0]["text"].splitlines() == [
        "交易时间\t流水号\t金额",
        "2026-07-17 10:00:00\tT001\t100.00",
        "2026-07-17 10:05:00\tT002\t200.00",
    ]


def test_image_chunk_has_full_image_region(tmp_path):
    from PIL import Image

    path = tmp_path / "statement.png"
    Image.new("RGB", (640, 480), "white").save(path)

    chunks = extract_material(path)

    assert chunks[0]["requires_vision"] is True
    assert chunks[0]["region"] == [0, 0, 640, 480]


def test_xlsx_row_data_is_json_serializable(tmp_path):
    import pandas as pd

    path = tmp_path / "statement.xlsx"
    pd.DataFrame([{"交易日期": datetime(2026, 7, 17, 10, 8, 9), "交易金额": 100}]).to_excel(
        path, index=False
    )

    chunks = extract_material(path)

    assert json.loads(json.dumps(chunks, ensure_ascii=False))[0]["row_data"]["交易日期"].startswith(
        "2026-07-17"
    )


def test_exact_duplicates_are_grouped_and_canonicalized():
    first = record("DUP-001")
    second = record("DUP-001").model_copy(
        update={"source": SourceLocation(source_file_id="FILE-2", page_number=1)}
    )

    grouped = group_duplicate_records([first, second])

    assert grouped[0].duplicate_group
    assert grouped[0].duplicate_group == grouped[1].duplicate_group
    assert len(canonical_records(grouped)) == 1


def test_same_serial_with_conflicting_fields_is_not_auto_merged():
    grouped = group_duplicate_records([record("CONFLICT-001"), record("CONFLICT-001", amount=1200)])

    assert all(item.duplicate_group is None for item in grouped)
    assert all(item.conflict_status == "same_serial_conflicting_fields" for item in grouped)
    assert len(canonical_records(grouped)) == 2


def test_exact_duplicate_partition_is_preserved_beside_conflicting_variant():
    first = record("MIXED-001")
    duplicate = record("MIXED-001")
    conflicting = record("MIXED-001", amount=1200)

    grouped = group_duplicate_records([first, duplicate, conflicting])

    assert grouped[0].duplicate_group == grouped[1].duplicate_group
    assert grouped[0].duplicate_group is not None
    assert grouped[2].duplicate_group is None
    assert all(item.conflict_status == "same_serial_conflicting_fields" for item in grouped)
    assert len(canonical_records(grouped)) == 2


def test_same_serial_at_different_time_or_currency_is_a_conflict():
    original = record("FIELDS-001")
    later = record("FIELDS-001").model_copy(
        update={"transaction_time": datetime(2026, 7, 17, 10, 1)}
    )
    other_currency = record("FIELDS-002").model_copy(update={"currency": "USD"})

    time_group = group_duplicate_records([original, later])
    currency_group = group_duplicate_records([record("FIELDS-002"), other_currency])

    assert all(item.conflict_status for item in time_group)
    assert all(item.duplicate_group is None for item in time_group)
    assert all(item.conflict_status for item in currency_group)
    assert all(item.duplicate_group is None for item in currency_group)


def test_transaction_time_is_normalized_to_timezone_free_business_time():
    payload = record("TZ-001").model_dump()
    payload["transaction_time"] = "2026-07-17T10:08:09Z"
    normalized = TransactionRecord.model_validate(payload)

    assert normalized.transaction_time == datetime(2026, 7, 17, 10, 8, 9)
    assert normalized.transaction_time.tzinfo is None


def test_concurrent_source_replacements_do_not_lose_records(tmp_path):
    repository = FileRepository(tmp_path)
    case = repository.create_case(CaseRecord(name="并发案", case_number="CONCURRENT-1"))

    def replace(index: int):
        item = record(f"SERIAL-{index:02d}").model_copy(
            update={"source": SourceLocation(source_file_id=f"FILE-{index:02d}")}
        )
        repository.replace_drafts_for_source(case.case_id, item.source.source_file_id, [item])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(replace, range(20)))

    assert len(repository.list_drafts(case.case_id)) == 20
