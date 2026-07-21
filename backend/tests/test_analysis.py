from datetime import datetime, timedelta

from app.analysis import attribute_mixed_funds, build_graph, count_rapid_transfers, trace_network
from app.models import TransactionRecord


def tx(index: int, amount: float) -> TransactionRecord:
    return TransactionRecord(
        transaction_id=f"T{index}", transaction_time=datetime(2026, 6, 18, 10) + timedelta(minutes=index),
        serial_number=f"SN{index}", payer_account="L1", payer_name="一级卡",
        payee_account=f"OUT{index}", payee_name=f"下游{index}", amount=amount,
        balance_after=0, review_status="confirmed",
    )


def test_mixed_funds_four_methods_never_exceed_victim_amount():
    transfers = [tx(i, amount) for i, amount in enumerate([10000] * 5 + [20000, 30000], 1)]
    results = attribute_mixed_funds(transfers, "L1", 50000, 50000)
    assert set(results) == {"fifo", "conservative", "possible_max", "proportional"}
    assert [item.attributed_amount for item in results["fifo"].edges[:5]] == [10000] * 5
    assert all(result.total_attributed == 50000 for result in results.values())
    assert all(result.is_inference for result in results.values())


def test_trace_network_returns_hops_shortest_path_and_cycles():
    records = [
        TransactionRecord(transaction_id="A", transaction_time=datetime(2026, 1, 1), payer_account="1", payer_name="1", payee_account="2", payee_name="2", amount=100, review_status="confirmed"),
        TransactionRecord(transaction_id="B", transaction_time=datetime(2026, 1, 2), payer_account="2", payer_name="2", payee_account="3", payee_name="3", amount=80, review_status="confirmed"),
        TransactionRecord(transaction_id="C", transaction_time=datetime(2026, 1, 3), payer_account="3", payer_name="3", payee_account="1", payee_name="1", amount=20, review_status="confirmed"),
    ]
    result = trace_network(records, start="1", end="3", hops=2)
    assert result["shortest_path"] == ["1", "2", "3"]
    assert set(result["downstream"]) == {"1", "2", "3"}
    assert result["cycles"] == [["1", "2", "3", "1"]]


def test_graph_risk_is_rule_based_explainable_and_time_ordered():
    base = datetime(2026, 6, 18, 10)
    records = [
        TransactionRecord(transaction_id="IN", transaction_time=base, payer_account="VICTIM", payer_name="受害人", payee_account="L1", payee_name="一级卡", amount=100000, summary="涉诈入金", review_status="confirmed"),
        TransactionRecord(transaction_id="OUT1", transaction_time=base + timedelta(minutes=5), payer_account="L1", payer_name="一级卡", payee_account="A", payee_name="下游A", amount=20000, summary="资金拆分", review_status="confirmed"),
        TransactionRecord(transaction_id="OUT2", transaction_time=base + timedelta(minutes=10), payer_account="L1", payer_name="一级卡", payee_account="B", payee_name="下游B", amount=20000, summary="资金拆分", review_status="confirmed"),
        TransactionRecord(transaction_id="OUT3", transaction_time=base + timedelta(minutes=15), payer_account="L1", payer_name="一级卡", payee_account="C", payee_name="下游C", amount=20000, summary="资金拆分", review_status="confirmed"),
        TransactionRecord(transaction_id="RETURN", transaction_time=base + timedelta(minutes=20), payer_account="C", payer_name="下游C", payee_account="L1", payee_name="一级卡", amount=5000, summary="资金回流", review_status="confirmed"),
    ]
    graph = build_graph(records)
    l1 = next(node for node in graph["nodes"] if node["id"] == "L1")
    factor_codes = {factor["code"] for factor in l1["risk_factors"]}
    assert {"rapid_transfer", "pass_through", "split_transfer", "return_flow"}.issubset(factor_codes)
    assert l1["risk"] == sum(factor["score"] for factor in l1["risk_factors"])
    assert 0 <= l1["risk"] <= 100
    assert graph["risk_summary"]["score"] == max(node["risk"] for node in graph["nodes"])
    assert graph["risk_summary"]["method"] == "internal_rules_v1"
    edge = next(edge for edge in graph["edges"] if edge["id"] == "L1>A")
    assert edge["first_transaction_time"] == (base + timedelta(minutes=5)).isoformat()


def test_rapid_transfer_count_uses_forward_time_window():
    base = datetime(2026, 6, 18, 10)
    incoming = [tx(1, 10000).model_copy(update={"transaction_time": base})]
    outgoing = [
        tx(2, 10000).model_copy(update={"transaction_time": base - timedelta(minutes=1)}),
        tx(3, 10000).model_copy(update={"transaction_time": base + timedelta(minutes=5)}),
        tx(4, 10000).model_copy(update={"transaction_time": base + timedelta(minutes=31)}),
    ]
    assert count_rapid_transfers(incoming, outgoing) == 1


def test_graph_counts_duplicate_group_only_once():
    base = datetime(2026, 7, 17, 10)
    records = [
        TransactionRecord(transaction_id="A", transaction_time=base, serial_number="SAME", payer_account="1", payer_name="甲", payee_account="2", payee_name="乙", amount=100, review_status="confirmed", duplicate_group="DUP-1"),
        TransactionRecord(transaction_id="B", transaction_time=base, serial_number="SAME", payer_account="1", payer_name="甲", payee_account="2", payee_name="乙", amount=100, review_status="confirmed", duplicate_group="DUP-1"),
    ]

    graph = build_graph(records)

    assert graph["transaction_count"] == 1
    assert graph["total_amount"] == 100
    assert graph["edges"][0]["count"] == 1
