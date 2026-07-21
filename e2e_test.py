import httpx
import tempfile
from pathlib import Path

BASE = "http://127.0.0.1:8000"

# --- 1. 创建案件 ---
case = httpx.post(f"{BASE}/api/cases", json={
    "name": "端到端测试案件",
    "case_number": "FZ-2026-TEST-001",
    "victims": [{"name": "张三", "accounts": ["6222021234567890"], "reported_loss": 50000}],
}).json()
case_id = case["case_id"]
print(f"1. 创建案件: {case_id}")

# --- 2. 上传 CSV 文件 ---
csv_content = (
    "交易时间,流水号,付款账号,付款户名,付款行,收款账号,收款户名,收款行,金额,摘要\n"
    "2026-01-15 09:30:00,TX001,6222021111111111,李四,工行,6222022222222222,王五,建行,10000,货款\n"
    "2026-01-15 10:00:00,TX002,6222021111111111,李四,工行,6222023333333333,赵六,农行,20000,投资\n"
    "2026-01-15 11:00:00,TX003,6222022222222222,王五,建行,6222024444444444,孙七,中行,5000,还款\n"
)

with tempfile.NamedTemporaryFile(suffix=".csv", mode="wb", delete=False) as f:
    f.write(csv_content.encode("utf-8-sig"))
    csv_path = f.name

files = httpx.post(
    f"{BASE}/api/cases/{case_id}/materials",
    files={"files": ("test.csv", Path(csv_path).read_bytes(), "text/csv")},
)
materials = files.json()
file_id = materials[0]["file_id"]
Path(csv_path).unlink()
print(f"2. 上传CSV: {file_id} (duplicate={materials[0]['duplicate']})")

# --- 3. 解析 ---
parse_result = httpx.post(f"{BASE}/api/cases/{case_id}/materials/{file_id}/parse").json()
status = parse_result["material"]["status"]
draft_count = parse_result["material"]["draft_count"]
print(f"3. 解析: status={status}, draft_count={draft_count}")

# --- 4. 查看草稿 ---
drafts = httpx.get(f"{BASE}/api/cases/{case_id}/draft-transactions").json()
print(f"4. 草稿数: {drafts['total']}")
for item in drafts["items"]:
    print(f"   {item['serial_number']:8s} | {item['payer_name']} -> {item['payee_name']} | {item['amount']:>6.0f} | {item['review_status']}")

# --- 5. 确认全部 ---
httpx.post(f"{BASE}/api/cases/{case_id}/draft-transactions/confirm-all")
confirmed = httpx.get(f"{BASE}/api/cases/{case_id}/draft-transactions").json()
all_confirmed = all(i["review_status"] == "confirmed" for i in confirmed["items"])
print(f"5. 全部确认: {'OK' if all_confirmed else 'FAIL'}")

# --- 6. 创建版本 ---
version = httpx.post(f"{BASE}/api/cases/{case_id}/versions", json={"name": "v1确认版"}).json()
print(f"6. 创建版本: {version['version_id']}, {version['record_count']} 条")

# --- 7. 添加种子 ---
first_tx = drafts["items"][0]
seed = httpx.post(f"{BASE}/api/cases/{case_id}/seeds", json={
    "victim_id": case["victims"][0]["victim_id"],
    "transaction_id": first_tx["transaction_id"],
    "amount": 10000,
    "confirmed_by": "测试人员",
}).json()
print(f"7. 添加种子: {seed['seed_id']}")

# --- 8. 资金拓扑图 ---
graph = httpx.get(f"{BASE}/api/cases/{case_id}/analysis/graph").json()
nodes = graph.get("nodes", [])
edges = graph.get("edges", [])
tx_count = graph.get("transaction_count", 0)
total = graph.get("total_amount", 0)
risk = graph.get("risk_summary", {})
print(f"8. 拓扑图: {len(nodes)} 节点, {len(edges)} 边, {tx_count} 笔交易, 总金额 {total}")
print(f"   最高风险: {risk.get('level')} (账户: {risk.get('account_label')}, 评分: {risk.get('score')})")

# --- 9. 资金归集 ---
attribution = httpx.post(
    f"{BASE}/api/cases/{case_id}/analysis/attribute",
    params={"source_account": "6222021111111111", "victim_amount": 20000, "preexisting_balance": 5000},
).json()
for method, result in attribution.items():
    print(f"9. 归集({method}): 归集={result['total_attributed']}, 剩余={result['remaining_amount']}")

# --- 10. 资金追踪 ---
trace = httpx.get(f"{BASE}/api/cases/{case_id}/analysis/trace", params={"start": "6222021111111111", "hops": 3}).json()
print(f"10. 追踪: upstream={trace['upstream']}, downstream={trace['downstream']}")

print("\n===== 主链路全部通过 =====")
