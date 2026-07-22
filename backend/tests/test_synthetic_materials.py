from collections import Counter
from pathlib import Path
import re

import pytest

from tools.generate_multisource_fixtures import (
    DISPLAY_HEADERS,
    ENTITY_BANKS,
    ENTITY_NAMES,
    _display_row,
    build_distribution,
    build_truth,
    generate_xlsx,
    validate_material_set,
)
from app.analysis.core import build_graph
from app.models import TransactionRecord
from app.parsing.classification import classify_chunk


def test_synthetic_entity_registry_uses_approved_realistic_names():
    expected_names = (
        "唐文博", "蒋雨欣", "罗静怡", "许志远",
        "彭嘉航", "何梦琪", "周启明", "蔡安然", "邓宇辰", "姚思宁", "韩泽凯", "苏婉清",
        "程浩然", "叶知秋", "魏俊驰", "沈依宁", "戴云舟", "陆可欣", "熊致远", "谭若琳",
        "长沙景程电子商务有限公司", "湖南远澜网络科技有限公司", "长沙市芙蓉区嘉禾百货商行",
        "湖南启辰电子贸易有限公司", "长沙汇泽商务咨询有限公司", "湖南云帆数码科技有限公司",
        "长沙市雨花区悦邻便利店", "长沙市天心区汇诚通讯商行", "湖南盛联数字技术有限公司",
        "中国建设银行长沙解放西路ATM", "长沙市开福区鑫悦烟酒商行", "跨境支付商户 NORTHSTAR DIGITAL",
    )

    assert ENTITY_NAMES == expected_names
    assert len(set(ENTITY_NAMES)) == 32
    assert ENTITY_BANKS == (
        "中国工商银行长沙分行",
        "中国农业银行长沙分行",
        "中国银行湖南省分行",
        "中国建设银行长沙分行",
        "交通银行长沙分行",
    )
    placeholder = re.compile(
        r"受害人[甲乙丙丁]|某(?:一|二|三|四|五|六|七|八|九|十)|商户[AB]|甲银行"
    )
    assert not any(placeholder.search(name) for name in ENTITY_NAMES + ENTITY_BANKS)
    truth = build_truth()
    assert tuple(entity["name"] for entity in truth["entities"]) == ENTITY_NAMES


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
