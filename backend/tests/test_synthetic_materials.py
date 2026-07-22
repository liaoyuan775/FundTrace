from collections import Counter
from pathlib import Path

import pytest

from tools.generate_multisource_fixtures import (
    DISPLAY_HEADERS,
    _display_row,
    build_distribution,
    build_truth,
    generate_xlsx,
    validate_material_set,
)
from app.analysis.core import build_graph
from app.models import TransactionRecord
from app.parsing.classification import classify_chunk


def test_synthetic_case_has_fixed_scale_and_multiformat_distribution():
    truth = build_truth()
    distribution = build_distribution(truth["transactions"])

    assert len(truth["entities"]) == 32
    assert len(truth["transactions"]) == 120
    assert len(distribution) == 10
    appearances = [transaction_id for item in distribution for transaction_id in item["transaction_ids"]]
    assert len(appearances) == 135
    assert len(set(appearances)) == 120
    assert sum(count - 1 for count in Counter(appearances).values()) == 15
    assert Counter(Path(item["filename"]).suffix for item in distribution) == {
        ".csv": 2,
        ".xlsx": 2,
        ".pdf": 2,
        ".docx": 2,
        ".png": 1,
        ".jpg": 1,
    }


def test_unstructured_material_rows_include_transaction_balance():
    transaction = build_truth()["transactions"][0]

    assert DISPLAY_HEADERS == [
        "交易时间",
        "流水号",
        "付款账号",
        "付款户名",
        "收款账号",
        "收款户名",
        "金额",
        "交易后余额",
        "渠道",
        "摘要",
    ]
    assert _display_row(transaction)[7] == f'{transaction["balance_after"]:.2f}'
    assert len(_display_row(transaction)) == len(DISPLAY_HEADERS)


def test_material_set_validation_rejects_missing_xlsx_files(tmp_path):
    (tmp_path / "materials").mkdir()

    with pytest.raises(RuntimeError, match="材料文件集合不完整"):
        validate_material_set(tmp_path)


def test_xlsx_generation_requires_explicit_artifact_runtime(tmp_path):
    with pytest.raises(RuntimeError, match="artifact-tool"):
        generate_xlsx(tmp_path, "node", "")


def test_synthetic_truth_reconciles_to_confirmed_topology_without_duplicates():
    truth = build_truth()
    records = [
        TransactionRecord(
            transaction_id=item["transaction_id"],
            transaction_time=item["transaction_time"],
            serial_number=item["serial_number"],
            payer_account=item["payer_account"],
            payer_name=item["payer_name"],
            payee_account=item["payee_account"],
            payee_name=item["payee_name"],
            amount=item["amount"],
            channel=item["channel"],
            summary=item["summary"],
            review_status="confirmed",
        )
        for item in truth["transactions"]
    ]
    graph = build_graph(records)

    assert graph["transaction_count"] == truth["expected_graph"]["transaction_count"]
    assert graph["total_amount"] == truth["expected_graph"]["total_amount"]
    assert len(graph["nodes"]) == truth["expected_graph"]["node_count"]
    assert classify_chunk(Path("statement.csv"), {"text": "商户号,终端号,授权码"})["record_type"] == "card_payment"


def test_statement_headers_override_atm_keyword_in_payee_name():
    result = classify_chunk(
        Path("statement.txt"),
        {"text": "交易日期 流水号 付款账号 收款账号 收款户名 ATM服务中心"},
    )

    assert result["document_type"] == "bank_statement"
    assert result["record_type"] == "bank_transfer"
