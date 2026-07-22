import concurrent.futures
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ..analysis.core import attribute_mixed_funds, build_graph, shortest_path, trace_network
from ..demo.data import demo_case, demo_transactions
from ..models import CaseCreate, CaseRecord, DraftUpdate, SeedCreate, SeedRecord, SourceLocation, TransactionRecord, VersionCreate
from ..parsing.extractors import UnsupportedMaterialError, extract_material
from ..parsing.classification import classify_chunk
from ..parsing.normalization import normalize_structured_row_with_status
from ..repository.file_repo import FileRepository
from .deps import get_qwen, get_repo, get_settings

router = APIRouter()


# ── Cases ──────────────────────────────────────────────────────────

@router.post("/api/cases", status_code=201, response_model=CaseRecord)
def create_case(payload: CaseCreate, repo: FileRepository = Depends(get_repo)):
    return repo.create_case(CaseRecord(**payload.model_dump()))


@router.get("/api/cases")
def list_cases(repo: FileRepository = Depends(get_repo)):
    return repo.list_cases()


@router.get("/api/cases/{case_id}")
def get_case(case_id: str, repo: FileRepository = Depends(get_repo)):
    try:
        return repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, "案件不存在")


@router.patch("/api/cases/{case_id}")
def archive_case(case_id: str, status: str, repo: FileRepository = Depends(get_repo)):
    case = repo.get_case(case_id)
    case.status = "archived" if status == "archived" else "active"
    return repo.save_case(case)


# ── Materials ──────────────────────────────────────────────────────

def _write_material_manifest(path: Path, manifest: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    temp.replace(path)


def _set_material_status(case_id: str, file_id: str, status: str, repo: FileRepository, **updates) -> dict:
    path = repo.case_dir(case_id) / "materials" / f"{file_id}.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest.update(status=status, **updates)
    _write_material_manifest(path, manifest)
    return manifest


def _parse_material_batch(case_id: str, file_ids: list[str], repo: FileRepository, qwen, settings) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(settings.qwen_domain_concurrency, len(file_ids))) as pool:
        futures = [
            pool.submit(parse_material, case_id, file_id, True, repo, qwen, settings)
            for file_id in file_ids
        ]
        for future in futures:
            try:
                future.result()
            except Exception:
                # The individual parser has already persisted the failure details.
                continue


@router.post("/api/cases/{case_id}/materials", status_code=201)
async def upload_materials(
    case_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(default=[]),
    repo: FileRepository = Depends(get_repo),
    qwen=Depends(get_qwen),
    settings=Depends(get_settings),
):
    target = repo.case_dir(case_id) / "materials"
    results = []
    for index, upload in enumerate(files):
        content = await upload.read()
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"文件超过{settings.max_upload_mb}MB限制")
        digest = hashlib.sha256(content).hexdigest()
        suffix = Path(upload.filename or "file").suffix.lower()
        stored = target / f"{digest}{suffix}"
        duplicate = stored.exists()
        if not duplicate:
            stored.write_bytes(content)
        submitted_path = relative_paths[index] if index < len(relative_paths) else (upload.filename or "file")
        normalized = Path(submitted_path.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise HTTPException(400, "非法文件夹相对路径")
        manifest = {
            "file_id": digest,
            "original_name": Path(upload.filename or "file").name,
            "relative_path": normalized.as_posix(),
            "stored_name": stored.name,
            "size": len(content),
            "sha256": digest,
            "duplicate": duplicate,
            "status": "queued",
        }
        _write_material_manifest(target / f"{digest}.json", manifest)
        results.append(manifest)
        repo.append_audit(case_id, {"event": "material_uploaded", "file_id": digest, "name": manifest["original_name"], "duplicate": duplicate})
    if results:
        background_tasks.add_task(
            _parse_material_batch,
            case_id,
            list(dict.fromkeys(item["file_id"] for item in results)),
            repo,
            qwen,
            settings,
        )
    return results


@router.get("/api/cases/{case_id}/materials")
def list_materials(case_id: str, repo: FileRepository = Depends(get_repo)):
    return [json.loads(p.read_text("utf-8")) for p in (repo.case_dir(case_id) / "materials").glob("*.json")]


@router.get("/api/cases/{case_id}/materials/{file_id}/download")
def download_material(case_id: str, file_id: str, repo: FileRepository = Depends(get_repo)):
    manifest_path = repo.case_dir(case_id) / "materials" / f"{file_id}.json"
    if not manifest_path.exists():
        raise HTTPException(404, "材料不存在")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    path = repo.case_dir(case_id) / "materials" / manifest["stored_name"]
    return FileResponse(path, filename=manifest["original_name"], media_type="application/octet-stream")


@router.post("/api/cases/{case_id}/materials/{file_id}/parse")
def parse_material(
    case_id: str,
    file_id: str,
    use_model: bool = False,
    repo: FileRepository = Depends(get_repo),
    qwen=Depends(get_qwen),
    settings=Depends(get_settings),
):
    material_dir = repo.case_dir(case_id) / "materials"
    manifest_path = material_dir / f"{file_id}.json"
    if not manifest_path.exists():
        raise HTTPException(404, "材料不存在")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    path = material_dir / manifest["stored_name"]
    _set_material_status(case_id, file_id, "parsing", repo)
    try:
        chunks = extract_material(path, settings.rar_executable)
    except UnsupportedMaterialError as exc:
        _set_material_status(case_id, file_id, "failed", repo, error_count=1, errors=[str(exc)])
        raise HTTPException(422, str(exc))
    except Exception as exc:
        _set_material_status(case_id, file_id, "failed", repo, error_count=1, errors=[f"材料读取失败: {type(exc).__name__}"])
        raise HTTPException(500, f"材料读取失败: {type(exc).__name__}") from exc
    extracted = repo.case_dir(case_id) / "extracted" / f"{file_id}.json"
    extracted.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), "utf-8")
    extracted_records = []
    errors = []
    warnings = []
    adapter = qwen

    # First pass: structured chunks inline (fast, no VLM needed)
    vlm_tasks = []
    for index, chunk in enumerate(chunks):
        chunk["classification"] = classify_chunk(path, chunk)
        source = SourceLocation(
            source_file_id=file_id,
            archive_member_path=chunk.get("archive_member_path"),
            page_number=chunk.get("page_number"),
            sheet_name=chunk.get("sheet_name"),
            table_number=chunk.get("table_number"),
            paragraph_number=chunk.get("paragraph_number"),
            row_number=chunk.get("row_number"),
            region=chunk.get("region"),
        )
        if chunk.get("row_data"):
            structured, rejection = normalize_structured_row_with_status(chunk["row_data"], source)
            if structured:
                structured.source = source
                extracted_records.append(structured)
            elif rejection:
                errors.append({
                    "chunk_index": index,
                    "page_number": chunk.get("page_number"),
                    "sheet_name": chunk.get("sheet_name"),
                    "row_number": chunk.get("row_number"),
                    "error": rejection,
                    "status": "needs_manual_review",
                })
        elif use_model:
            vlm_tasks.append((index, chunk, source))

    # Process VLM chunks concurrently (8 workers)
    if vlm_tasks:
        def _vlm_parse(index: int, chunk: dict, source: SourceLocation) -> tuple:
            local_adapter = adapter
            text = chunk.get("text", "")
            image = Path(chunk["image_path"]) if chunk.get("image_path") else None
            try:
                if (
                    chunk["classification"]["record_type"] == "unknown"
                    and local_adapter.enabled
                ):
                    chunk["classification"] = local_adapter.classify(
                        text, image
                    ).model_dump()
                records = local_adapter.normalize(
                    text,
                    image,
                    chunk["classification"]["record_type"],
                )
                w = local_adapter.last_warning
                rw = local_adapter.retry_warnings
                return (index, records, w, rw, None, chunk, source)
            except RuntimeError as exc:
                rw = local_adapter.retry_warnings
                return (index, [], None, rw, str(exc), chunk, source)

        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.qwen_domain_concurrency) as pool:
            futures = [pool.submit(_vlm_parse, *t) for t in vlm_tasks]
            for future in concurrent.futures.as_completed(futures):
                index, records, warning, retry_warnings, error, chunk_obj, chunk_source = future.result()
                if error:
                    chunk = chunks[index]
                    errors.append({
                        "chunk_index": index,
                        "page_number": chunk.get("page_number"),
                        "sheet_name": chunk.get("sheet_name"),
                        "row_number": chunk.get("row_number"),
                        "error": error,
                        "retry_warnings": retry_warnings,
                    })
                    continue
                if warning and warning not in warnings:
                    warnings.append(warning)
                for rw in retry_warnings:
                    if rw not in warnings:
                        warnings.append(rw)
                for record in records:
                    record_source = chunk_source.model_copy(deep=True)
                    if record_source.table_number is not None:
                        serial = "".join(c for c in record.serial_number.upper() if c.isalnum())
                        matches = [
                            item["row_number"]
                            for item in chunk_obj.get("row_evidence", [])
                            if serial and serial in "".join(c for c in item["text"].upper() if c.isalnum())
                        ]
                        record_source.row_number = matches[0] if len(matches) == 1 else None
                    record.source = record_source
                    record.evidence_locations = [record_source.model_copy(deep=True)]
                    extracted_records.append(record)
    created = repo.reconcile_drafts_for_source(case_id, file_id, extracted_records, replace_missing=not errors) if extracted_records or use_model else []
    # Persist classifications and any model-updated chunk metadata alongside
    # the raw extraction so later audits can reproduce schema routing.
    extracted.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), "utf-8")
    if errors:
        status = "partial" if created else "failed"
    else:
        status = "parsed" if created or use_model else "extracted"
    manifest["status"] = status
    manifest["chunk_count"] = len(chunks)
    manifest["draft_count"] = len(created)
    manifest["error_count"] = len(errors)
    manifest["warning_count"] = len(warnings)
    manifest["errors"] = errors
    manifest["warnings"] = warnings
    _write_material_manifest(manifest_path, manifest)
    return {"material": manifest, "chunks": chunks[:50], "drafts": created, "errors": errors, "warnings": warnings}


# ── Draft Transactions ─────────────────────────────────────────────

@router.post("/api/cases/{case_id}/draft-transactions", status_code=201)
def add_draft(case_id: str, payload: TransactionRecord, repo: FileRepository = Depends(get_repo)):
    return repo.add_draft(case_id, payload)


@router.get("/api/cases/{case_id}/draft-transactions")
def list_drafts(
    case_id: str,
    page: int = 1,
    page_size: int = Query(100, le=500),
    query: str = "",
    status: str = "",
    min_amount: float = 0,
    direction: str = "all",
    channel: str = "",
    bank: str = "",
    region: str = "",
    date_from: str = "",
    date_to: str = "",
    sort: str = "time_asc",
    repo: FileRepository = Depends(get_repo),
):
    records = repo.list_drafts(case_id)
    q = query.lower()
    records = [x for x in records if x.amount >= min_amount and (not q or q in " ".join([x.serial_number, x.payer_account, x.payer_name, x.payee_account, x.payee_name, x.summary]).lower()) and (not status or x.review_status == status) and (direction == "all" or (direction == "return" and "回流" in x.summary) or (direction == "forward" and "回流" not in x.summary)) and (not channel or x.channel == channel) and (not bank or bank in x.payer_bank or bank in x.payee_bank) and (not region or x.region == region) and (not date_from or x.transaction_time.date().isoformat() >= date_from) and (not date_to or x.transaction_time.date().isoformat() <= date_to)]
    sorters = {"time_asc": lambda x: x.transaction_time, "time_desc": lambda x: x.transaction_time, "amount_desc": lambda x: x.amount}
    records.sort(key=sorters.get(sort, sorters["time_asc"]), reverse=sort in {"time_desc", "amount_desc"})
    start = (page - 1) * page_size
    return {"items": records[start:start + page_size], "total": len(records), "page": page, "page_size": page_size}


@router.patch("/api/cases/{case_id}/draft-transactions/{transaction_id}")
def update_draft(case_id: str, transaction_id: str, payload: DraftUpdate, repo: FileRepository = Depends(get_repo)):
    try:
        return repo.update_draft(case_id, transaction_id, payload.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "流水不存在")


@router.post("/api/cases/{case_id}/draft-transactions/confirm-all")
def confirm_all(case_id: str, repo: FileRepository = Depends(get_repo)):
    records = repo.list_drafts(case_id)
    for record in records:
        if record.review_status == "pending":
            repo.update_draft(case_id, record.transaction_id, {"review_status": "confirmed", "review_note": "批量人工确认"})
    return {"confirmed": len(records)}


@router.get("/api/cases/{case_id}/evidence/{transaction_id}")
def evidence(case_id: str, transaction_id: str, repo: FileRepository = Depends(get_repo)):
    record = next((x for x in repo.list_drafts(case_id) if x.transaction_id == transaction_id), None)
    if not record:
        raise HTTPException(404, "流水不存在")
    return {"transaction": record, "source": record.source, "provenance": record.provenance, "review_note": record.review_note}


# ── Versions ───────────────────────────────────────────────────────

@router.post("/api/cases/{case_id}/versions", status_code=201)
def create_version(case_id: str, payload: VersionCreate, repo: FileRepository = Depends(get_repo)):
    try:
        return repo.create_version(case_id, payload.name)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/api/cases/{case_id}/versions")
def versions(case_id: str, repo: FileRepository = Depends(get_repo)):
    return repo.list_versions(case_id)


@router.get("/api/cases/{case_id}/versions/{version_id}/download")
def download_version(case_id: str, version_id: str, repo: FileRepository = Depends(get_repo)):
    path = repo.case_dir(case_id) / "versions" / f"{version_id}.csv"
    if not path.exists():
        raise HTTPException(404, "版本不存在")
    return FileResponse(path, filename=f"{case_id}-{version_id}-confirmed.csv", media_type="text/csv")


@router.get("/api/cases/{case_id}/exports/transactions")
def export_transactions(case_id: str, repo: FileRepository = Depends(get_repo)):
    versions = repo.list_versions(case_id)
    if not versions:
        raise HTTPException(409, "请先生成确认版本")
    version = versions[-1]
    return FileResponse(repo.case_dir(case_id) / version.csv_path, filename=f"{case_id}-{version.version_id}.csv", media_type="text/csv")


# ── Seeds ──────────────────────────────────────────────────────────

def _confirmed_records(repo: FileRepository, case_id: str) -> list[TransactionRecord]:
    return [
        record
        for record in repo.list_drafts(case_id)
        if record.review_status == "confirmed"
    ]


@router.post("/api/cases/{case_id}/seeds", status_code=201)
def add_seed(case_id: str, payload: SeedCreate, repo: FileRepository = Depends(get_repo)):
    try:
        case = repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, "案件不存在")
    victim = next(
        (item for item in case.victims if item.victim_id == payload.victim_id),
        None,
    )
    if victim is None:
        raise HTTPException(409, "所选受害人不存在")
    record = next((x for x in repo.list_drafts(case_id) if x.transaction_id == payload.transaction_id), None)
    if not record or record.review_status != "confirmed":
        raise HTTPException(409, "起点必须来自已确认流水")
    victim_accounts = {
        "".join(character for character in account if character.isalnum())
        for account in victim.accounts
    }
    if record.payer_account not in victim_accounts:
        raise HTTPException(409, "起点流水的付款账号必须属于所选受害人")
    return repo.save_seed(case_id, SeedRecord(**payload.model_dump()))


@router.get("/api/cases/{case_id}/seeds")
def seeds(case_id: str, repo: FileRepository = Depends(get_repo)):
    return repo.list_seeds(case_id)


@router.delete("/api/cases/{case_id}/seeds/{seed_id}")
def delete_seed(case_id: str, seed_id: str, repo: FileRepository = Depends(get_repo)):
    try:
        repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, "案件不存在")
    if not repo.delete_seed(case_id, seed_id):
        raise HTTPException(404, "涉诈起点不存在")
    return {"seed_id": seed_id, "status": "cancelled"}


# ── Analysis ───────────────────────────────────────────────────────

@router.get("/api/cases/{case_id}/analysis/graph")
def graph(
    case_id: str,
    query: str = "",
    min_amount: float = 0,
    direction: str = "all",
    channel: str = "",
    bank: str = "",
    region: str = "",
    date_from: str = "",
    date_to: str = "",
    repo: FileRepository = Depends(get_repo),
):
    case = repo.get_case(case_id)
    victim_accounts = {
        "".join(character for character in account if character.isalnum())
        for victim in case.victims
        for account in victim.accounts
    }
    return build_graph(
        _confirmed_records(repo, case_id),
        query,
        min_amount,
        direction,
        channel,
        bank,
        region,
        date_from,
        date_to,
        victim_accounts,
    )


@router.get("/api/cases/{case_id}/analysis/path")
def path(case_id: str, start: str, end: str, repo: FileRepository = Depends(get_repo)):
    return {"path": shortest_path(_confirmed_records(repo, case_id), start, end)}


@router.get("/api/cases/{case_id}/analysis/trace")
def trace(case_id: str, start: str, end: str = "", hops: int = Query(3, ge=1, le=8), repo: FileRepository = Depends(get_repo)):
    return trace_network(_confirmed_records(repo, case_id), start, end, hops)


@router.post("/api/cases/{case_id}/analysis/attribute")
def attribute(case_id: str, source_account: str, victim_amount: float, preexisting_balance: float = 0, repo: FileRepository = Depends(get_repo)):
    return attribute_mixed_funds(_confirmed_records(repo, case_id), source_account, victim_amount, preexisting_balance)


# ── Demo ───────────────────────────────────────────────────────────

@router.post("/api/demo/bootstrap", status_code=201)
def bootstrap(repo: FileRepository = Depends(get_repo)):
    existing = next((case for case in repo.list_cases() if case.case_number == "FZ-2026-0716-09"), None)
    if existing:
        return {"case_id": existing.case_id, "created": False}
    case = repo.create_case(demo_case())
    repo.save_drafts(case.case_id, demo_transactions())
    repo.create_version(case.case_id, "演示确认版")
    return {"case_id": case.case_id, "created": True}
