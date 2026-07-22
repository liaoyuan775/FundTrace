# Batch 01 Entity Renaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every placeholder-style person, company, merchant, bank, and exit name in Batch 01 with the approved fictional entity registry, regenerate all ten source materials and oracle files, then rerun isolated ingestion and topology reconciliation.

**Architecture:** `tools/generate_multisource_fixtures.py` remains the single source of truth for entity identity and transaction generation. Every CSV, PDF, DOCX, image, XLSX, distribution entry, and oracle record is regenerated from that truth; `tools/generate_multisource_xlsx.mjs` continues to consume `ground_truth.json` and must not duplicate entity names. The existing ingestion runner uploads only `materials/`, reads the oracle after parsing, and writes machine-readable and Markdown reports.

**Tech Stack:** Python 3.12, pytest, ReportLab, python-docx, Pillow, Node.js, `@oai/artifact-tool`, FastAPI TestClient, Qwen strict JSON Schema.

## Global Constraints

- All people, companies, merchants, accounts, and amounts remain completely fictional.
- Retain real bank and payment-institution names; do not restore `甲银行` through `戊银行`.
- Preserve exactly 32 entities, 120 unique transactions, 135 material appearances, and 15 duplicate groups.
- Preserve every account, serial number, timestamp, amount, balance, channel, edge, and expected topology value.
- Do not upload `oracle/` or use it as model input.
- Do not commit `.env`, `backend/data/`, preserved case directories, or unrelated dirty-worktree changes.

---

### Task 1: Make the Approved Entity Registry Executable

**Files:**
- Modify: `tools/generate_multisource_fixtures.py:12-55`
- Modify: `backend/tests/test_synthetic_materials.py:1-40`

**Interfaces:**
- Consumes: the approved mapping in `docs/superpowers/specs/2026-07-22-batch-01-entity-naming-design.md`.
- Produces: `ENTITY_NAMES: tuple[str, ...]`, `ENTITY_BANKS: tuple[str, ...]`, and `build_truth() -> dict` with stable account-to-name mapping.

- [ ] **Step 1: Add a failing registry test**

Add imports and a test that asserts the exact approved name sequence, real bank names, unique names, stable account mapping, and absence of placeholder patterns:

```python
import re

from tools.generate_multisource_fixtures import ENTITY_BANKS, ENTITY_NAMES


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
        "中国工商银行长沙分行", "中国农业银行长沙分行", "中国银行湖南省分行",
        "中国建设银行长沙分行", "交通银行长沙分行",
    )
    assert not any(re.search(r"受害人[甲乙丙丁]|某(?:一|二|三|四|五|六|七|八|九|十)|商户[AB]|甲银行", name) for name in ENTITY_NAMES + ENTITY_BANKS)
    truth = build_truth()
    assert tuple(entity["name"] for entity in truth["entities"]) == ENTITY_NAMES
```

- [ ] **Step 2: Run the focused test and verify the red state**

Run:

```powershell
D:\Python\python.exe -m pytest backend/tests/test_synthetic_materials.py -q -k approved_realistic_names
```

Expected: collection or assertion failure because `ENTITY_NAMES` and `ENTITY_BANKS` do not exist yet.

- [ ] **Step 3: Implement the registry as the only identity source**

Define immutable tuples at module scope and update `build_truth()` to index them:

```python
ENTITY_BANKS = (
    "中国工商银行长沙分行",
    "中国农业银行长沙分行",
    "中国银行湖南省分行",
    "中国建设银行长沙分行",
    "交通银行长沙分行",
)

ENTITY_NAMES = (
    "唐文博", "蒋雨欣", "罗静怡", "许志远",
    "彭嘉航", "何梦琪", "周启明", "蔡安然", "邓宇辰", "姚思宁", "韩泽凯", "苏婉清",
    "程浩然", "叶知秋", "魏俊驰", "沈依宁", "戴云舟", "陆可欣", "熊致远", "谭若琳",
    "长沙景程电子商务有限公司", "湖南远澜网络科技有限公司", "长沙市芙蓉区嘉禾百货商行",
    "湖南启辰电子贸易有限公司", "长沙汇泽商务咨询有限公司", "湖南云帆数码科技有限公司",
    "长沙市雨花区悦邻便利店", "长沙市天心区汇诚通讯商行", "湖南盛联数字技术有限公司",
    "中国建设银行长沙解放西路ATM", "长沙市开福区鑫悦烟酒商行", "跨境支付商户 NORTHSTAR DIGITAL",
)
```

Replace local `banks` and `names` with `ENTITY_BANKS` and `ENTITY_NAMES`. Keep the existing role ordering and account generation unchanged.

- [ ] **Step 4: Verify registry and topology invariants**

Run:

```powershell
D:\Python\python.exe -m pytest backend/tests/test_synthetic_materials.py -q
```

Expected: all synthetic-material tests pass, including 32 nodes, 120 transactions, 135 appearances, and 15 duplicates.

- [ ] **Step 5: Commit only registry source and test**

```powershell
git add tools/generate_multisource_fixtures.py backend/tests/test_synthetic_materials.py
git commit -m "test: replace batch 01 placeholder entities"
```

Before committing, inspect the staged diff because both files may contain pre-existing user changes; stage only hunks belonging to this task.

---

### Task 2: Regenerate All Ten Materials and Oracle Files

**Files:**
- Regenerate: `test-data/batch-01/materials/*`
- Regenerate: `test-data/batch-01/oracle/ground_truth.json`
- Regenerate: `test-data/batch-01/oracle/distribution.json`
- Regenerate: `test-data/batch-01/oracle/file_manifest.csv`
- Verify without modification: `tools/generate_multisource_xlsx.mjs`

**Interfaces:**
- Consumes: `build_truth()`, `build_distribution()`, `generate_materials(output_dir, node, artifact_tool_module)`.
- Produces: exactly ten uploadable materials and three oracle files using the same 32-name registry.

- [ ] **Step 1: Locate bundled Node and artifact-tool runtimes**

Use the workspace dependency loader and verify both returned paths exist. The expected Windows paths are:

```powershell
$node = "C:\Users\86136\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$artifact = "C:\Users\86136\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\@oai\artifact-tool\dist\artifact_tool.mjs"
Test-Path $node
Test-Path $artifact
```

Expected: both commands return `True`. If runtime discovery returns different absolute paths, use the discovered values.

- [ ] **Step 2: Regenerate the target batch**

Run:

```powershell
D:\Python\python.exe tools\generate_multisource_fixtures.py test-data\batch-01 --node $node --artifact-tool-module $artifact
```

Expected JSON summary: `transactions=120`, `appearances=135`, `files=10`.

- [ ] **Step 3: Verify generated names and immutable transaction fields**

Run a read-only check against the new oracle:

```powershell
D:\Python\python.exe -c "import json,re; from pathlib import Path; p=Path('test-data/batch-01/oracle/ground_truth.json'); x=json.loads(p.read_text(encoding='utf-8')); names={e['name'] for e in x['entities']}; old=re.compile(r'受害人[甲乙丙丁]|某(?:一|二|三|四|五|六|七|八|九|十)|商户[AB]|甲银行'); assert len(names)==32; assert not any(old.search(n) for n in names); assert len(x['transactions'])==120; assert len(x['duplicate_transaction_ids'])==15; assert x['expected_graph']=={'node_count':32,'edge_count':112,'transaction_count':120,'total_amount':2928760.0}; print({'entities':len(names),'transactions':len(x['transactions']),'duplicates':len(x['duplicate_transaction_ids']),'graph':x['expected_graph']})"
```

Expected: the printed dictionary contains 32 entities, 120 transactions, 15 duplicates, 112 edges, and total amount `2928760.0`.

- [ ] **Step 4: Verify all material formats remain readable**

Run:

```powershell
D:\Python\python.exe -m pytest backend/tests/test_synthetic_materials.py backend/tests/test_ingestion.py -q
```

Expected: all selected tests pass. Then inspect the two generated raster files and the first page of each PDF to confirm that long company names fit and remain legible; DOCX and XLSX validation must use their structured parsers rather than filename checks.

- [ ] **Step 5: Commit only regenerated canonical fixtures**

```powershell
git add tools/generate_multisource_xlsx.mjs test-data/batch-01/materials test-data/batch-01/oracle
git commit -m "test: regenerate batch 01 with realistic entities"
```

Do not stage preserved `case-data-*` directories or old ingestion reports. If `generate_multisource_xlsx.mjs` has no task-specific diff, do not stage it.

---

### Task 3: Rebuild an Isolated Case and Reconcile the Topology

**Files:**
- Generate: `test-data/batch-01/test_report.json`
- Generate: `test-data/batch-01/test_report.md`
- Generate and keep untracked: `test-data/batch-01/case-data-entity-renaming/`
- Verify: `tools/run_multisource_ingestion.py`

**Interfaces:**
- Consumes: `run(output_dir: Path, data_dir: Path) -> dict` and the ten regenerated materials.
- Produces: per-format extraction accuracy, duplicate handling, evidence coverage, model capability, and graph reconciliation.

- [ ] **Step 1: Ensure the isolated case directory is new and empty**

Use `test-data/batch-01/case-data-entity-renaming/`. If it already exists, choose a new timestamped sibling instead of deleting unrelated data.

- [ ] **Step 2: Run real upload and model extraction**

Run:

```powershell
D:\Python\python.exe tools\run_multisource_ingestion.py test-data\batch-01 --data-dir test-data\batch-01\case-data-entity-renaming
```

Expected: all ten files upload. Text and structured formats are reconciled against the new oracle. If the current Qwen service still reports `vision_attempted=true` and `vision=false`, the two image failures must remain explicit in the report rather than being counted as successful extraction.

- [ ] **Step 3: Verify report identity and graph assertions**

Run:

```powershell
D:\Python\python.exe -c "import json,re; from pathlib import Path; r=json.loads(Path('test-data/batch-01/test_report.json').read_text(encoding='utf-8')); assert r['upload_count']==10; assert r['false_positive_count']==0; assert not any(re.search(r'受害人[甲乙丙丁]|某(?:一|二|三|四|五|六|七|八|九|十)|商户[AB]|甲银行', str(x)) for x in r.get('mismatch_details',[])); print({'passed':r['passed'],'drafts':r['draft_count'],'canonical':r['canonical_count'],'duplicates':r['duplicate_group_count'],'graph':r['graph'],'model':r['model_capability']})"
```

Expected when text and vision are both available: 135 drafts, 120 canonical transactions, 15 duplicate groups, 32 nodes, 112 edges, 120 graph transactions, total amount `2928760.0`, and `passed=true`. When vision is unavailable, report the exact two failed image files and the reduced draft/canonical counts; do not weaken acceptance thresholds or fabricate image results.

- [ ] **Step 4: Run the complete automated suite once**

Run:

```powershell
D:\Python\python.exe -m pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 5: Review delivery diff and report**

Run:

```powershell
git diff --check
git status --short
```

Confirm that every task-specific changed line maps to the approved name registry or regenerated fixtures. Keep runtime case data untracked. Commit `test_report.json` and `test_report.md` only if the repository intentionally tracks current acceptance reports; otherwise leave them as local evidence and summarize their measured outcome.
