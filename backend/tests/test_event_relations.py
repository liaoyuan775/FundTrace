from datetime import datetime

from app.analysis.core import build_graph
from app.models import SourceLocation, TransactionRecord


def record(**updates) -> TransactionRecord:
    values = {
        "transaction_id": "T1",
        "transaction_time": datetime(2026, 7, 22, 10),
        "payer_account": "A",
        "payer_name": "甲",
        "payee_account": "B",
        "payee_name": "乙",
        "amount": 100,
        "review_status": "confirmed",
        "event_status": "success",
    }
    values.update(updates)
    return TransactionRecord(**values)


def test_topology_only_accepts_confirmed_successful_funds_events():
    records = [
        record(transaction_id="OK"),
        record(transaction_id="PENDING", review_status="pending"),
        record(transaction_id="FAILED", event_status="failed"),
        record(transaction_id="EVIDENCE", relation_type="corroborates"),
    ]

    graph = build_graph(records)

    assert graph["transaction_count"] == 1
    assert graph["edges"][0]["transaction_ids"] == ["OK"]


def test_pos_and_atm_use_explicit_entity_endpoints_without_invented_accounts():
    pos = record(
        transaction_id="POS",
        payee_account="",
        payee_name="测试商户",
        payee_entity_type="merchant",
        payee_endpoint_id="MERCHANT:M001",
        merchant_id="M001",
    )
    atm = record(
        transaction_id="ATM",
        payer_account="B",
        payer_name="乙",
        payee_account="",
        payee_name="ATM终端",
        payee_entity_type="atm",
        payee_endpoint_id="ATM:T001",
        terminal_id="T001",
    )

    graph = build_graph([pos, atm])

    assert {edge["target"] for edge in graph["edges"]} == {"MERCHANT:M001", "ATM:T001"}
    assert {node["entity_type"] for node in graph["nodes"] if node["id"].startswith(("MERCHANT:", "ATM:"))} == {"merchant", "atm"}


def test_multiple_evidence_locations_are_preserved():
    tx = record(
        source=SourceLocation(source_file_id="FILE-A", row_number=2),
        evidence_locations=[
            SourceLocation(source_file_id="FILE-A", row_number=2),
            SourceLocation(source_file_id="FILE-B", page_number=3),
        ],
        related_transaction_id="ORIGINAL",
        relation_type="refunds",
    )

    dumped = tx.model_dump(mode="json")

    assert len(dumped["evidence_locations"]) == 2
    assert dumped["relation_type"] == "refunds"
