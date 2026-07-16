from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.demo import demo_transactions
from app.config import Settings


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
