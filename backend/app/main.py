import hashlib
import json
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analysis import attribute_mixed_funds, build_graph, shortest_path, trace_network
from .config import Settings, get_settings
from .demo import demo_case, demo_transactions
from .models import CaseCreate, CaseRecord, DraftUpdate, SeedCreate, SeedRecord, TransactionRecord, VersionCreate
from .parsers import UnsupportedMaterialError, extract_material, sha256_file
from .qwen import QwenAdapter
from .repository import FileRepository


def create_app(settings: Settings | None=None) -> FastAPI:
    settings=settings or get_settings(); repo=FileRepository(settings.data_dir)
    app=FastAPI(title="FundTrace API",version="0.1.0")
    app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:5173","http://localhost:5173"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
    app.state.settings=settings;app.state.repo=repo;app.state.qwen=QwenAdapter(settings)

    def repository():return app.state.repo
    @app.get("/api/health")
    def health():return {"status":"ok","storage":"files","model":app.state.qwen.probe().model_dump()}
    @app.post("/api/cases",status_code=201,response_model=CaseRecord)
    def create_case(payload:CaseCreate,r:FileRepository=Depends(repository)):return r.create_case(CaseRecord(**payload.model_dump()))
    @app.get("/api/cases")
    def list_cases(r:FileRepository=Depends(repository)):return r.list_cases()
    @app.get("/api/cases/{case_id}")
    def get_case(case_id:str,r:FileRepository=Depends(repository)):
        try:return r.get_case(case_id)
        except KeyError:raise HTTPException(404,"案件不存在")
    @app.patch("/api/cases/{case_id}")
    def archive_case(case_id:str,status:str,r:FileRepository=Depends(repository)):
        case=r.get_case(case_id);case.status="archived" if status=="archived" else "active";return r.save_case(case)

    @app.post("/api/cases/{case_id}/materials",status_code=201)
    async def upload_materials(case_id:str,files:list[UploadFile]=File(...),relative_paths:list[str]=Form(default=[]),r:FileRepository=Depends(repository)):
        target=r.case_dir(case_id)/"materials";results=[]
        for index,upload in enumerate(files):
            content=await upload.read()
            if len(content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,f"文件超过{settings.max_upload_mb}MB限制")
            digest=hashlib.sha256(content).hexdigest();suffix=Path(upload.filename or "file").suffix.lower();stored=target/f"{digest}{suffix}"
            duplicate=stored.exists()
            if not duplicate:stored.write_bytes(content)
            submitted_path=relative_paths[index] if index<len(relative_paths) else (upload.filename or "file")
            normalized=Path(submitted_path.replace("\\","/"))
            if normalized.is_absolute() or ".." in normalized.parts:raise HTTPException(400,"非法文件夹相对路径")
            manifest={"file_id":digest,"original_name":Path(upload.filename or "file").name,"relative_path":normalized.as_posix(),"stored_name":stored.name,"size":len(content),"sha256":digest,"duplicate":duplicate,"status":"uploaded"}
            (target/f"{digest}.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),"utf-8");results.append(manifest)
            r.append_audit(case_id,{"event":"material_uploaded","file_id":digest,"name":manifest["original_name"],"duplicate":duplicate})
        return results
    @app.get("/api/cases/{case_id}/materials")
    def list_materials(case_id:str,r:FileRepository=Depends(repository)):
        return [json.loads(p.read_text("utf-8")) for p in (r.case_dir(case_id)/"materials").glob("*.json")]
    @app.get("/api/cases/{case_id}/materials/{file_id}/download")
    def download_material(case_id:str,file_id:str,r:FileRepository=Depends(repository)):
        manifest_path=r.case_dir(case_id)/"materials"/f"{file_id}.json"
        if not manifest_path.exists():raise HTTPException(404,"材料不存在")
        manifest=json.loads(manifest_path.read_text("utf-8"));path=r.case_dir(case_id)/"materials"/manifest["stored_name"]
        return FileResponse(path,filename=manifest["original_name"],media_type="application/octet-stream")
    @app.post("/api/cases/{case_id}/materials/{file_id}/parse")
    def parse_material(case_id:str,file_id:str,use_model:bool=False,r:FileRepository=Depends(repository)):
        material_dir=r.case_dir(case_id)/"materials";manifest_path=material_dir/f"{file_id}.json"
        if not manifest_path.exists():raise HTTPException(404,"材料不存在")
        manifest=json.loads(manifest_path.read_text("utf-8"));path=material_dir/manifest["stored_name"]
        try:chunks=extract_material(path,settings.rar_executable)
        except UnsupportedMaterialError as exc:raise HTTPException(422,str(exc))
        extracted=r.case_dir(case_id)/"extracted"/f"{file_id}.json";extracted.write_text(json.dumps(chunks,ensure_ascii=False,indent=2),"utf-8")
        created=[]
        if use_model:
            adapter=QwenAdapter(settings)
            for chunk in chunks:
                try:
                    records=adapter.normalize(chunk.get("text",""),Path(chunk["image_path"]) if chunk.get("image_path") else None)
                    for record in records:
                        record.source.source_file_id=file_id;record.source.page_number=chunk.get("page_number");record.source.sheet_name=chunk.get("sheet_name");record.source.row_number=chunk.get("row_number");r.add_draft(case_id,record);created.append(record)
                except RuntimeError:continue
        manifest["status"]="parsed";manifest["chunk_count"]=len(chunks);manifest["draft_count"]=len(created);manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),"utf-8")
        return {"material":manifest,"chunks":chunks[:50],"drafts":created}

    @app.post("/api/cases/{case_id}/draft-transactions",status_code=201)
    def add_draft(case_id:str,payload:TransactionRecord,r:FileRepository=Depends(repository)):return r.add_draft(case_id,payload)
    @app.get("/api/cases/{case_id}/draft-transactions")
    def list_drafts(case_id:str,page:int=1,page_size:int=Query(100,le=500),query:str="",status:str="",min_amount:float=0,direction:str="all",channel:str="",bank:str="",region:str="",date_from:str="",date_to:str="",sort:str="time_asc",r:FileRepository=Depends(repository)):
        records=r.list_drafts(case_id);q=query.lower();records=[x for x in records if x.amount>=min_amount and (not q or q in " ".join([x.serial_number,x.payer_account,x.payer_name,x.payee_account,x.payee_name,x.summary]).lower()) and (not status or x.review_status==status) and (direction=="all" or (direction=="return" and "回流" in x.summary) or (direction=="forward" and "回流" not in x.summary)) and (not channel or x.channel==channel) and (not bank or bank in x.payer_bank or bank in x.payee_bank) and (not region or x.region==region) and (not date_from or x.transaction_time.date().isoformat()>=date_from) and (not date_to or x.transaction_time.date().isoformat()<=date_to)]
        sorters={"time_asc":lambda x:x.transaction_time,"time_desc":lambda x:x.transaction_time,"amount_desc":lambda x:x.amount};records.sort(key=sorters.get(sort,sorters["time_asc"]),reverse=sort in {"time_desc","amount_desc"})
        start=(page-1)*page_size;return {"items":records[start:start+page_size],"total":len(records),"page":page,"page_size":page_size}
    @app.patch("/api/cases/{case_id}/draft-transactions/{transaction_id}")
    def update_draft(case_id:str,transaction_id:str,payload:DraftUpdate,r:FileRepository=Depends(repository)):
        try:return r.update_draft(case_id,transaction_id,payload.model_dump(exclude_unset=True))
        except KeyError:raise HTTPException(404,"流水不存在")
    @app.post("/api/cases/{case_id}/draft-transactions/confirm-all")
    def confirm_all(case_id:str,r:FileRepository=Depends(repository)):
        records=r.list_drafts(case_id)
        for record in records:
            if record.review_status=="pending":r.update_draft(case_id,record.transaction_id,{"review_status":"confirmed","review_note":"批量人工确认"})
        return {"confirmed":len(records)}
    @app.post("/api/cases/{case_id}/versions",status_code=201)
    def create_version(case_id:str,payload:VersionCreate,r:FileRepository=Depends(repository)):
        try:return r.create_version(case_id,payload.name)
        except ValueError as exc:raise HTTPException(409,str(exc))
    @app.get("/api/cases/{case_id}/versions")
    def versions(case_id:str,r:FileRepository=Depends(repository)):return r.list_versions(case_id)
    @app.get("/api/cases/{case_id}/versions/{version_id}/download")
    def download_version(case_id:str,version_id:str,r:FileRepository=Depends(repository)):
        path=r.case_dir(case_id)/"versions"/f"{version_id}.csv"
        if not path.exists():raise HTTPException(404,"版本不存在")
        return FileResponse(path,filename=f"{case_id}-{version_id}-confirmed.csv",media_type="text/csv")
    @app.post("/api/cases/{case_id}/seeds",status_code=201)
    def add_seed(case_id:str,payload:SeedCreate,r:FileRepository=Depends(repository)):
        record=next((x for x in r.list_drafts(case_id) if x.transaction_id==payload.transaction_id),None)
        if not record or record.review_status!="confirmed":raise HTTPException(409,"起点必须来自已确认流水")
        return r.save_seed(case_id,SeedRecord(**payload.model_dump()))
    @app.get("/api/cases/{case_id}/seeds")
    def seeds(case_id:str,r:FileRepository=Depends(repository)):return r.list_seeds(case_id)
    @app.get("/api/cases/{case_id}/analysis/graph")
    def graph(case_id:str,query:str="",min_amount:float=0,direction:str="all",channel:str="",bank:str="",region:str="",date_from:str="",date_to:str="",r:FileRepository=Depends(repository)):return build_graph(r.list_drafts(case_id),query,min_amount,direction,channel,bank,region,date_from,date_to)
    @app.get("/api/cases/{case_id}/analysis/path")
    def path(case_id:str,start:str,end:str,r:FileRepository=Depends(repository)):return {"path":shortest_path(r.list_drafts(case_id),start,end)}
    @app.get("/api/cases/{case_id}/analysis/trace")
    def trace(case_id:str,start:str,end:str="",hops:int=Query(3,ge=1,le=8),r:FileRepository=Depends(repository)):return trace_network(r.list_drafts(case_id),start,end,hops)
    @app.post("/api/cases/{case_id}/analysis/attribute")
    def attribute(case_id:str,source_account:str,victim_amount:float,preexisting_balance:float=0,r:FileRepository=Depends(repository)):return attribute_mixed_funds(r.list_drafts(case_id),source_account,victim_amount,preexisting_balance)
    @app.get("/api/cases/{case_id}/evidence/{transaction_id}")
    def evidence(case_id:str,transaction_id:str,r:FileRepository=Depends(repository)):
        record=next((x for x in r.list_drafts(case_id) if x.transaction_id==transaction_id),None)
        if not record:raise HTTPException(404,"流水不存在")
        return {"transaction":record,"source":record.source,"provenance":record.provenance,"review_note":record.review_note}
    @app.get("/api/cases/{case_id}/exports/transactions")
    def export_transactions(case_id:str,r:FileRepository=Depends(repository)):
        versions=r.list_versions(case_id)
        if not versions:raise HTTPException(409,"请先生成确认版本")
        version=versions[-1];return FileResponse(r.case_dir(case_id)/version.csv_path,filename=f"{case_id}-{version.version_id}.csv",media_type="text/csv")
    @app.post("/api/demo/bootstrap",status_code=201)
    def bootstrap(r:FileRepository=Depends(repository)):
        existing=next((case for case in r.list_cases() if case.case_number=="FZ-2026-0716-09"),None)
        if existing:return {"case_id":existing.case_id,"created":False}
        case=r.create_case(demo_case());r.save_drafts(case.case_id,demo_transactions());r.create_version(case.case_id,"演示确认版")
        return {"case_id":case.case_id,"created":True}
    frontend_dist=Path(__file__).resolve().parents[2]/"frontend"/"dist"
    if frontend_dist.exists():
        app.mount("/",StaticFiles(directory=frontend_dist,html=True),name="frontend")
    return app


app=create_app()
