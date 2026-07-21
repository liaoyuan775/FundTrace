from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.demo.data import demo_transactions
from app.config import Settings
from app.models import TransactionRecord


def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path, qwen_api_key="", qwen_base_url="")))


def test_case_lifecycle_and_review_gate(tmp_path):
    api = client(tmp_path)
    created = api.post("/api/cases", json={"name": "0716专案", "case_number": "FZ-0716", "victims": []})
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    draft = {"transaction_id":"T001","transaction_time":"2026-06-18T10:00:00","serial_number":"SN001","payer_account":"62170001","payer_name":"受害人甲","payee_account":"62280001","payee_name":"一级卡甲","amount":50000,"balance_after":1200,"review_status":"pending"}
    assert api.post(f"/api/cases/{case_id}/draft-transactions", json=draft).status_code == 201
    assert api.post(f"/api/cases/{case_id}/versions", json={"name":"v1"}).status_code == 409
    assert api.patch(f"/api/cases/{case_id}/draft-transactions/T001", json={"review_status":"confirmed","review_note":"已核对"}).status_code == 200
    version = api.post(f"/api/cases/{case_id}/versions", json={"name":"v1"})
    assert version.status_code == 201 and version.json()["record_count"] == 1


def test_demo_bootstrap_has_complex_graph(tmp_path):
    api = client(tmp_path)
    response = api.post("/api/demo/bootstrap")
    assert response.status_code == 201
    graph = api.get(f"/api/cases/{response.json()['case_id']}/analysis/graph").json()
    assert len(graph["nodes"]) >= 48
    assert len(graph["edges"]) >= 60


def test_demo_graph_entities_are_account_holders_not_scam_scenarios():
    forbidden = ("入金池", "收款池", "退款池", "任务池")
    names = {
        name
        for transaction in demo_transactions()
        for name in (transaction.payer_name, transaction.payee_name)
    }

    assert not [name for name in names if any(word in name for word in forbidden)]


def test_duplicate_material_is_identified_by_hash(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/api/cases", json={"name":"重复材料案","case_number":"DUP-1","victims":[]}).json()["case_id"]
    files = [("files", ("flow.csv", b"time,amount\n2026-01-01,100", "text/csv"))]
    first = api.post(f"/api/cases/{case_id}/materials", files=files).json()[0]
    second = api.post(f"/api/cases/{case_id}/materials", files=files).json()[0]
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["sha256"] == second["sha256"]


def test_settings_load_named_qwen_environment_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QWEN_BASE_URL", "http://intranet.example/v1")
    monkeypatch.setenv("QWEN_API_KEY", "secret-value")
    monkeypatch.setenv("QWEN_MODEL", "Qwen-Test")
    settings = Settings()
    assert settings.data_dir == tmp_path
    assert settings.qwen_base_url == "http://intranet.example/v1"
    assert settings.qwen_api_key == "secret-value"
    assert settings.qwen_model == "Qwen-Test"


def test_parse_material_reports_failed_model_chunks(tmp_path, monkeypatch):
    api = client(tmp_path)
    case_id = api.post("/api/demo/bootstrap").json()["case_id"]
    uploaded = api.post(
        f"/api/cases/{case_id}/materials",
        files=[("files", ("statement.txt", b"unsupported body", "text/plain"))],
    )
    assert uploaded.status_code == 201
    file_id = uploaded.json()[0]["file_id"]

    monkeypatch.setattr("app.api.routes.extract_material", lambda *_: [{"text": "一笔流水"}])
    monkeypatch.setattr("app.ai.qwen.QwenAdapter.normalize", lambda *_: (_ for _ in ()).throw(RuntimeError("model unavailable")))

    response = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse?use_model=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["material"]["status"] == "failed"
    assert payload["material"]["error_count"] == 1
    assert payload["errors"][0]["error"] == "model unavailable"


def test_reparsing_the_same_material_replaces_source_drafts(tmp_path):
    api = client(tmp_path)
    case_id = api.post(
        "/api/cases", json={"name": "幂等解析案", "case_number": "IDEMP-1", "victims": []}
    ).json()["case_id"]
    body = (
        "交易时间,流水号,付款账号,付款户名,收款账号,收款户名,金额\n"
        "2026-07-17 10:00:00,T001,62220001,甲,62220002,乙,100.00\n"
    ).encode("utf-8-sig")
    upload = api.post(
        f"/api/cases/{case_id}/materials",
        files=[("files", ("statement.csv", body, "text/csv"))],
    )
    file_id = upload.json()[0]["file_id"]

    first = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse")
    second = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse")
    drafts = api.get(f"/api/cases/{case_id}/draft-transactions").json()

    assert first.json()["material"]["draft_count"] == 1
    assert second.json()["material"]["draft_count"] == 1
    assert first.json()["drafts"][0]["transaction_id"] == second.json()["drafts"][0]["transaction_id"]
    assert drafts["total"] == 1


def test_failed_reparse_keeps_previous_source_drafts(tmp_path, monkeypatch):
    api = client(tmp_path)
    case_id = api.post(
        "/api/cases", json={"name": "失败重跑案", "case_number": "RETRY-1", "victims": []}
    ).json()["case_id"]
    upload = api.post(
        f"/api/cases/{case_id}/materials",
        files=[("files", ("statement.png", b"image", "image/png"))],
    )
    file_id = upload.json()[0]["file_id"]
    monkeypatch.setattr("app.api.routes.extract_material", lambda *_: [{"text": "", "image_path": "unused.png", "region": [0, 0, 1, 1]}])
    model_record = TransactionRecord(transaction_time="2026-07-17T10:00:00", serial_number="T1", payer_account="1", payer_name="甲", payee_account="2", payee_name="乙", amount=100)
    monkeypatch.setattr("app.ai.qwen.QwenAdapter.normalize", lambda *_: [model_record])
    first = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse?use_model=true")
    monkeypatch.setattr("app.ai.qwen.QwenAdapter.normalize", lambda *_: (_ for _ in ()).throw(RuntimeError("temporary failure")))

    second = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse?use_model=true")
    drafts = api.get(f"/api/cases/{case_id}/draft-transactions").json()

    assert first.json()["material"]["draft_count"] == 1
    assert second.json()["material"]["status"] == "failed"
    assert second.json()["material"]["draft_count"] == 0
    assert drafts["total"] == 1


def test_successful_reparse_preserves_human_confirmed_edits(tmp_path):
    api = client(tmp_path)
    case_id = api.post(
        "/api/cases", json={"name": "人工修改保留案", "case_number": "HUMAN-1", "victims": []}
    ).json()["case_id"]
    body = (
        "交易时间,流水号,付款账号,付款户名,收款账号,收款户名,金额\n"
        "2026-07-17 10:00:00,T001,62220001,原始户名,62220002,乙,100.00\n"
    ).encode("utf-8-sig")
    upload = api.post(f"/api/cases/{case_id}/materials", files=[("files", ("statement.csv", body, "text/csv"))])
    file_id = upload.json()[0]["file_id"]
    first = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse").json()["drafts"][0]
    api.patch(
        f"/api/cases/{case_id}/draft-transactions/{first['transaction_id']}",
        json={"review_status": "confirmed", "payer_name": "人工核定户名", "review_note": "已核对"},
    )

    second = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse").json()["drafts"][0]

    assert second["transaction_id"] == first["transaction_id"]
    assert second["payer_name"] == "人工核定户名"
    assert second["review_status"] == "confirmed"


def test_docx_batch_records_receive_table_and_row_evidence(tmp_path, monkeypatch):
    api = client(tmp_path)
    case_id = api.post(
        "/api/cases", json={"name": "证据定位案", "case_number": "EVID-1", "victims": []}
    ).json()["case_id"]
    upload = api.post(
        f"/api/cases/{case_id}/materials",
        files=[("files", ("statement.docx", b"placeholder", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    file_id = upload.json()[0]["file_id"]
    monkeypatch.setattr(
        "app.api.routes.extract_material",
        lambda *_: [{"text": "table", "table_number": 2, "row_evidence": [
            {"row_number": 2, "text": "T2\t2\t3\t200"},
            {"row_number": 3, "text": "T1\t1\t2\t100"},
        ]}],
    )
    monkeypatch.setattr(
        "app.ai.qwen.QwenAdapter.normalize",
        lambda *_: [
            TransactionRecord(transaction_time="2026-07-17T10:00:00", serial_number="T1", payer_account="1", payer_name="甲", payee_account="2", payee_name="乙", amount=100),
            TransactionRecord(transaction_time="2026-07-17T10:01:00", serial_number="T2", payer_account="2", payer_name="乙", payee_account="3", payee_name="丙", amount=200),
        ],
    )

    response = api.post(f"/api/cases/{case_id}/materials/{file_id}/parse?use_model=true")

    sources = [item["source"] for item in response.json()["drafts"]]
    assert [source["table_number"] for source in sources] == [2, 2]
    assert [source["row_number"] for source in sources] == [3, 2]


def test_confirmed_version_exports_one_canonical_duplicate(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/api/cases", json={"name":"重复流水案","case_number":"DUP-TX","victims":[]}).json()["case_id"]
    base = {"transaction_time":"2026-07-17T10:00:00","serial_number":"SAME-001","payer_account":"62170001","payer_name":"甲","payee_account":"62280001","payee_name":"乙","amount":5000,"review_status":"confirmed"}
    assert api.post(f"/api/cases/{case_id}/draft-transactions", json={**base,"transaction_id":"A"}).status_code == 201
    assert api.post(f"/api/cases/{case_id}/draft-transactions", json={**base,"transaction_id":"B"}).status_code == 201

    version = api.post(f"/api/cases/{case_id}/versions", json={"name":"去重确认版"})

    assert version.status_code == 201
    assert version.json()["record_count"] == 1
