import argparse
import json
import mimetypes
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


CRITICAL_FIELDS = (
    "transaction_time",
    "serial_number",
    "payer_account",
    "payer_name",
    "payee_account",
    "payee_name",
    "currency",
    "amount",
    "channel",
)


def _comparable(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat()
    if isinstance(value, float):
        return round(value, 2)
    return value


def _write_report(output_dir: Path, report: dict) -> None:
    (output_dir / "test_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    lines = [
        "# 多来源资金材料解析与拓扑测试报告",
        "",
        f"- 测试结果：{'通过' if report['passed'] else '未通过'}",
        f"- 上传材料：{report['upload_count']} / 10",
        f"- 草稿证据记录：{report['draft_count']} / 135",
        f"- 唯一交易：{report['canonical_count']} / 120",
        f"- 重复组：{report['duplicate_group_count']} / 15",
        f"- 误识别记录：{report['false_positive_count']}",
        "",
        "## 模型能力预检",
        "",
        f"- 已启用：{report['model_capability']['enabled']}",
        f"- 可达：{report['model_capability']['reachable']}",
        f"- 文本 JSON：{report['model_capability']['text_json']}",
        f"- 图片预检：{report['model_capability']['vision_preflight']}",
        f"- 图片已尝试：{report['model_capability']['vision_attempted']}",
        f"- 图片有效成功：{report['model_capability']['vision']}",
        f"- 探测信息：{report['model_capability']['message']}",
        "",
        "## 各格式准确率",
        "",
        "| 格式 | 期望记录 | 完全正确 | 准确率 | 漏识别 | 字段不符 | 多识别 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for suffix, metrics in sorted(report["format_metrics"].items()):
        lines.append(
            f"| {suffix} | {metrics['expected']} | {metrics['correct']} | "
            f"{metrics['accuracy']:.2%} | {metrics['missing']} | "
            f"{metrics['mismatched']} | {metrics['extra']} |"
        )
    graph = report["graph"]
    lines.extend(
        [
            "",
            "## 拓扑对账",
            "",
            f"- 节点：{graph['actual']['node_count']} / {graph['expected']['node_count']}",
            f"- 边：{graph['actual']['edge_count']} / {graph['expected']['edge_count']}",
            f"- 交易数：{graph['actual']['transaction_count']} / {graph['expected']['transaction_count']}",
            f"- 总金额：{graph['actual']['total_amount']:.2f} / {graph['expected']['total_amount']:.2f}",
            "",
            "## 解析状态与异常",
            "",
        ]
    )
    for item in report["materials"]:
        lines.append(
            f"- `{item['filename']}`：{item['status']}，提取 {item['draft_count']} 条，"
            f"错误 {item['error_count']}，警告 {item['warning_count']}"
        )
    if report["failures"]:
        lines.extend(["", "## 未通过项", ""])
        lines.extend(f"- {failure}" for failure in report["failures"])
    (output_dir / "test_report.md").write_text("\n".join(lines) + "\n", "utf-8")


def run(output_dir: Path, data_dir: Path) -> dict:
    output_dir = output_dir.resolve()
    data_dir = data_dir.resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        raise RuntimeError(f"隔离数据目录必须为空: {data_dir}")
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=data_dir)
    app = create_app(settings)
    adapter = app.state.qwen
    preflight_capability = adapter.probe()
    client = TestClient(app)
    case = client.post(
        "/api/cases",
        json={"name": "多来源资金材料合成测试案", "case_number": "SYN-2026-0717", "victims": []},
    )
    case.raise_for_status()
    case_id = case.json()["case_id"]
    uploads = {}
    material_results = []
    materials = sorted(path for path in (output_dir / "materials").iterdir() if path.is_file())
    for index, path in enumerate(materials, 1):
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as handle:
            response = client.post(
                f"/api/cases/{case_id}/materials",
                files=[("files", (path.name, handle, mime))],
            )
        response.raise_for_status()
        manifest = response.json()[0]
        uploads[path.name] = manifest
        print(f"[{index}/10] 已上传并开始解析: {path.name}", flush=True)
        parsed = client.post(
            f"/api/cases/{case_id}/materials/{manifest['file_id']}/parse?use_model=true"
        )
        parsed.raise_for_status()
        payload = parsed.json()
        result = {
            "filename": path.name,
            "suffix": path.suffix.lower(),
            "status": payload["material"]["status"],
            "draft_count": payload["material"]["draft_count"],
            "error_count": payload["material"]["error_count"],
            "warning_count": payload["material"]["warning_count"],
            "errors": payload["errors"],
            "warnings": payload["warnings"],
        }
        material_results.append(result)
        print(
            f"[{index}/10] {result['status']}: {result['draft_count']} 条，"
            f"错误 {result['error_count']}，警告 {result['warning_count']}",
            flush=True,
        )

    effective_capability = adapter.probe()
    model_capability = {
        "enabled": adapter.enabled,
        "reachable": effective_capability.reachable,
        "text_json": effective_capability.text_json,
        "vision_preflight": preflight_capability.vision,
        "vision_attempted": getattr(
            effective_capability,
            "vision_attempted",
            getattr(adapter, "vision_attempted", effective_capability.vision),
        ),
        "vision": effective_capability.vision,
        "message": effective_capability.message,
    }

    # The oracle is read only after every material has been parsed. It is never
    # uploaded, copied into the case, or passed to the extraction model.
    truth = json.loads((output_dir / "oracle" / "ground_truth.json").read_text("utf-8"))
    distribution = json.loads((output_dir / "oracle" / "distribution.json").read_text("utf-8"))
    truth_by_id = {item["transaction_id"]: item for item in truth["transactions"]}
    drafts_response = client.get(
        f"/api/cases/{case_id}/draft-transactions?page=1&page_size=500"
    )
    drafts_response.raise_for_status()
    drafts = drafts_response.json()["items"]
    source_names = {manifest["file_id"]: name for name, manifest in uploads.items()}
    actual_by_file = defaultdict(list)
    for record in drafts:
        actual_by_file[source_names[record["source"]["source_file_id"]]].append(record)

    format_metrics = defaultdict(lambda: {
        "expected": 0, "correct": 0, "missing": 0, "mismatched": 0, "extra": 0,
    })
    mismatch_details = []
    for spec in distribution:
        suffix = Path(spec["filename"]).suffix.lower()
        metrics = format_metrics[suffix]
        expected_rows = [truth_by_id[transaction_id] for transaction_id in spec["transaction_ids"]]
        expected_by_serial = {item["serial_number"]: item for item in expected_rows}
        actual_by_serial = {item["serial_number"]: item for item in actual_by_file[spec["filename"]]}
        metrics["expected"] += len(expected_rows)
        for serial, expected in expected_by_serial.items():
            actual = actual_by_serial.get(serial)
            if actual is None:
                metrics["missing"] += 1
                mismatch_details.append({"file": spec["filename"], "serial": serial, "issue": "missing"})
                continue
            mismatches = {}
            for field in CRITICAL_FIELDS:
                actual_value = _comparable(actual[field])
                expected_value = _comparable(expected[field])
                if actual_value != expected_value:
                    mismatches[field] = {"actual": actual_value, "expected": expected_value}
            if mismatches:
                metrics["mismatched"] += 1
                mismatch_details.append({"file": spec["filename"], "serial": serial, "fields": mismatches})
            else:
                metrics["correct"] += 1
        extras = set(actual_by_serial) - set(expected_by_serial)
        metrics["extra"] += len(extras)
        mismatch_details.extend(
            {"file": spec["filename"], "serial": serial, "issue": "extra"}
            for serial in sorted(extras)
        )
    for metrics in format_metrics.values():
        metrics["accuracy"] = metrics["correct"] / metrics["expected"] if metrics["expected"] else 0

    duplicate_groups = Counter(
        record["duplicate_group"] for record in drafts if record["duplicate_group"]
    )
    canonical_count = len(drafts) - sum(count - 1 for count in duplicate_groups.values())
    conflict_count = sum(bool(record["conflict_status"]) for record in drafts)
    def has_evidence(record: dict) -> bool:
        source = record["source"]
        if not source["source_file_id"]:
            return False
        suffix = Path(source_names[source["source_file_id"]]).suffix.lower()
        if suffix in {".csv", ".xlsx"}:
            return bool(source["sheet_name"] and source["row_number"])
        if suffix == ".pdf":
            return bool(source["page_number"])
        if suffix == ".docx":
            return bool(
                (source.get("table_number") and source["row_number"])
                or source.get("paragraph_number")
            )
        if suffix in {".png", ".jpg"}:
            return bool(source["region"] and len(source["region"]) == 4)
        return bool(source.get("archive_member_path"))

    evidence_count = sum(has_evidence(record) for record in drafts)
    confirm_response = client.post(f"/api/cases/{case_id}/draft-transactions/confirm-all")
    confirm_response.raise_for_status()
    version_response = client.post(
        f"/api/cases/{case_id}/versions", json={"name": "多来源解析确认版"}
    )
    version_record_count = None
    if version_response.status_code == 201:
        version_record_count = version_response.json()["record_count"]

    graph_response = client.get(f"/api/cases/{case_id}/analysis/graph")
    graph_response.raise_for_status()
    graph = graph_response.json()
    actual_graph = {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "transaction_count": graph["transaction_count"],
        "total_amount": round(graph["total_amount"], 2),
    }
    expected_graph = truth["expected_graph"]

    failures = []
    if len(uploads) != 10:
        failures.append(f"材料上传数为 {len(uploads)}，期望 10")
    if any(item["status"] != "parsed" for item in material_results):
        failures.append("存在未完全解析的材料")
    if len(drafts) != 135:
        failures.append(f"草稿证据记录为 {len(drafts)}，期望 135")
    if canonical_count != 120:
        failures.append(f"唯一交易为 {canonical_count}，期望 120")
    if len(duplicate_groups) != 15 or any(count != 2 for count in duplicate_groups.values()):
        failures.append("15 个跨文件重复组未全部正确识别")
    if conflict_count:
        failures.append(f"出现 {conflict_count} 条非预期冲突记录")
    if evidence_count != len(drafts):
        failures.append("存在无法追溯到原始文件的记录")
    if version_record_count != 120:
        failures.append(f"确认版本包含 {version_record_count} 条，期望 120")
    if actual_graph != expected_graph:
        failures.append("拓扑节点、边、交易数或总金额与真值不一致")
    for suffix, metrics in format_metrics.items():
        threshold = 1.0 if suffix in {".csv", ".xlsx"} else 0.9
        if metrics["accuracy"] < threshold:
            failures.append(f"{suffix} 准确率 {metrics['accuracy']:.2%} 低于 {threshold:.0%}")
    false_positive_count = sum(item["extra"] for item in format_metrics.values())
    if false_positive_count:
        failures.append(f"产生 {false_positive_count} 条真值外交易")

    report = {
        "passed": not failures,
        "case_id": case_id,
        "upload_count": len(uploads),
        "draft_count": len(drafts),
        "canonical_count": canonical_count,
        "duplicate_group_count": len(duplicate_groups),
        "conflict_count": conflict_count,
        "evidence_location_count": evidence_count,
        "version_record_count": version_record_count,
        "false_positive_count": false_positive_count,
        "model_capability": model_capability,
        "format_metrics": dict(format_metrics),
        "graph": {"actual": actual_graph, "expected": expected_graph},
        "materials": material_results,
        "mismatch_details": mismatch_details,
        "failures": failures,
    }
    _write_report(output_dir, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_dir, args.data_dir)
    print(json.dumps({"passed": result["passed"], "failures": result["failures"]}, ensure_ascii=False), flush=True)
    raise SystemExit(0 if result["passed"] else 1)
