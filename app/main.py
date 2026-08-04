from __future__ import annotations
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import settings
from .db import execute, init_db, row, rows, upsert_opportunity
from .domain import MUNICIPALITIES, opportunity_status, score_relevance
from .notifications import send_all
from .sync import run_sync
from .workflow import decorate, ensure_workflow_schema, mark_seen, notify_if_needed

STATIC_DIR = Path(__file__).parent / "static"

async def scheduler_loop():
    try:
        await asyncio.to_thread(run_sync)
    except Exception:
        pass

    while True:
        await asyncio.sleep(max(60, settings.sync_interval_minutes * 60))
        try:
            await asyncio.to_thread(run_sync)
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_workflow_schema()
    task = asyncio.create_task(scheduler_loop())
    yield
    task.cancel()

app = FastAPI(title="Radar Licita ISP API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def home(): return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
def health(): return {"status":"ok","service":settings.app_name,"time":datetime.now(timezone.utc).isoformat()}

@app.get("/api/municipalities")
def municipalities(): return [{"code":c,"name":n} for c,n in MUNICIPALITIES.items()]

@app.get("/api/dashboard")
def dashboard():
    stats = row("""SELECT COUNT(*) total, SUM(CASE WHEN status='aberta' THEN 1 ELSE 0 END) open, SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) favorites, SUM(CASE WHEN score>=70 THEN 1 ELSE 0 END) hot, MAX(updated_at) last_update FROM opportunities WHERE dismissed=0""") or {}
    by_city = rows("SELECT municipality, COUNT(*) total, ROUND(AVG(score),1) avg_score FROM opportunities WHERE dismissed=0 GROUP BY municipality ORDER BY total DESC")
    by_category = rows("SELECT category, COUNT(*) total FROM opportunities WHERE dismissed=0 GROUP BY category ORDER BY total DESC LIMIT 8")
    latest_sync = row("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
    return {"stats":stats,"by_city":by_city,"by_category":by_category,"latest_sync":latest_sync}

@app.get("/api/opportunities")
def opportunities(city: Optional[str] = None, min_score: int = Query(0, ge=0, le=100), max_score: Optional[int] = Query(None, ge=0, le=100), status: Optional[str] = None, category: Optional[str] = None, q: Optional[str] = None, favorite: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    where=["dismissed=0","score>=?"]; params: List[Any]=[min_score]
    if max_score is not None: where.append("score<=?"); params.append(max_score)
    if city: where.append("municipality_code=?"); params.append(city)
    if status: where.append("status=?"); params.append(status)
    if category: where.append("category=?"); params.append(category)
    if favorite: where.append("favorite=1")
    if q: where.append("(title LIKE ? OR description LIKE ? OR agency LIKE ?)"); term=f"%{q}%"; params += [term,term,term]
    sql=f"SELECT * FROM opportunities WHERE {' AND '.join(where)} ORDER BY favorite DESC, score DESC, COALESCE(proposal_end_at,'9999') ASC, id DESC LIMIT ? OFFSET ?"
    params += [limit,offset]
    data=rows(sql,params)
    for item in data:
        try: item["matched_terms"] = json.loads(item.get("matched_terms") or "[]")
        except json.JSONDecodeError: item["matched_terms"] = []
    return [decorate(item) for item in data]

@app.get("/api/opportunities/{opportunity_id}")
def opportunity(opportunity_id:int):
    item=row("SELECT * FROM opportunities WHERE id=?",(opportunity_id,))
    if not item: raise HTTPException(404,"Oportunidade não encontrada")
    mark_seen(opportunity_id)
    item=row("SELECT * FROM opportunities WHERE id=?",(opportunity_id,))
    return decorate(item)

@app.patch("/api/opportunities/{opportunity_id}/viewed")
def mark_opportunity_viewed(opportunity_id:int):
    item=row("SELECT id FROM opportunities WHERE id=?",(opportunity_id,))
    if not item: raise HTTPException(404,"Oportunidade não encontrada")
    mark_seen(opportunity_id)
    return {"viewed": True}

@app.patch("/api/opportunities/{opportunity_id}/favorite")
def toggle_favorite(opportunity_id:int):
    item=row("SELECT favorite FROM opportunities WHERE id=?",(opportunity_id,))
    if not item: raise HTTPException(404,"Oportunidade não encontrada")
    new=0 if item["favorite"] else 1; execute("UPDATE opportunities SET favorite=?,updated_at=? WHERE id=?",(new,datetime.now(timezone.utc).isoformat(),opportunity_id)); return {"favorite":bool(new)}

@app.patch("/api/opportunities/{opportunity_id}/dismiss")
def dismiss(opportunity_id:int):
    execute("UPDATE opportunities SET dismissed=1,updated_at=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),opportunity_id)); return {"dismissed":True}

@app.post("/api/opportunities/{opportunity_id}/notify")
def notify_now(opportunity_id:int):
    item=row("SELECT * FROM opportunities WHERE id=?",(opportunity_id,))
    if not item: raise HTTPException(404,"Oportunidade não encontrada")
    return notify_if_needed(item, force=True)

@app.post("/api/sync")
def sync_now(background_tasks: BackgroundTasks, wait: bool = False):
    if wait: return run_sync()
    background_tasks.add_task(run_sync); return {"status":"scheduled","message":"Sincronização iniciada"}

@app.get("/api/sync-runs")
def sync_runs(): return rows("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 30")



@app.post("/api/notifications/test")
def test_notifications():
    sample = {
        "id": 0,
        "municipality": "Santo Amaro",
        "agency": "Radar Licita Ti.Net",
        "category": "Teste de notificações",
        "score": 100,
        "title": "Teste do sistema de notificações do Radar de Licitações",
        "estimated_value": None,
        "proposal_end_at": "Teste manual",
        "url": "http://localhost:8080",
    }
    results = send_all(sample)
    sent = [x for x in results if x.get("status") == "sent"]
    errors = [x for x in results if x.get("status") == "error"]
    return {
        "ok": bool(sent) and not errors,
        "sent": len(sent),
        "errors": len(errors),
        "results": results,
    }

@app.get("/api/notifications")
def notifications(): return rows("SELECT n.*,o.title,o.municipality FROM notifications n LEFT JOIN opportunities o ON o.id=n.opportunity_id ORDER BY n.id DESC LIMIT 100")

class ManualOpportunity(BaseModel):
    municipality_code: str
    title: str = Field(min_length=5)
    description: str = ""
    agency: str = "Órgão público"
    modality: str = "Importação manual"
    notice_number: str = ""
    published_at: Optional[str] = None
    proposal_end_at: Optional[str] = None
    estimated_value: Optional[float] = None
    url: Optional[str] = None

@app.post("/api/opportunities/manual")
def manual(payload: ManualOpportunity):
    if payload.municipality_code not in MUNICIPALITIES: raise HTTPException(400,"Município inválido")
    score,terms,category=score_relevance(payload.title,payload.description)
    ext=f"manual:{payload.municipality_code}:{abs(hash((payload.title,payload.notice_number,payload.proposal_end_at)))}"
    item={"external_id":ext,"source":"Manual","municipality_code":payload.municipality_code,"municipality":MUNICIPALITIES[payload.municipality_code],"agency":payload.agency,"title":payload.title,"description":payload.description or payload.title,"modality":payload.modality,"notice_number":payload.notice_number,"published_at":payload.published_at,"proposal_end_at":payload.proposal_end_at,"estimated_value":payload.estimated_value,"url":payload.url,"score":score,"matched_terms":terms,"category":category,"status":opportunity_status(payload.proposal_end_at),"raw":payload.model_dump()}
    action,oid=upsert_opportunity(item); return {"id":oid,"action":action,"score":score,"category":category,"matched_terms":terms}

@app.post("/api/demo/load")
def load_demo():
    samples=[
      ("2929206","Contratação de link dedicado de acesso à internet em fibra óptica","Prestação de serviço de conectividade com IP público, SLA e suporte 24x7.","Secretaria de Administração",280000,"2026-08-14T09:00:00"),
      ("2904902","Fornecimento e instalação de rede Wi-Fi e cabeamento estruturado","Switches gerenciáveis, access points, rack, patch panel e certificação da rede.","Secretaria de Educação",198500,"2026-08-02T10:00:00"),
      ("2928604","Manutenção e expansão de rede FTTH GPON","Fusão de fibra óptica, caixas, drop óptico, SFP, OLT e atendimento técnico.","Prefeitura Municipal",420000,"2026-08-20T08:30:00"),
      ("2929750","Serviço de videomonitoramento com câmeras IP","Implantação de CFTV, conectividade, switches PoE e central de monitoramento.","Secretaria de Segurança",350000,"2026-08-11T09:00:00"),
    ]
    result=[]
    for i,(code,title,desc,agency,value,end) in enumerate(samples,1):
        score,terms,cat=score_relevance(title,desc)
        item={"external_id":f"demo:{i}","source":"Demonstração","municipality_code":code,"municipality":MUNICIPALITIES[code],"agency":agency,"title":title,"description":desc,"modality":"Pregão Eletrônico","notice_number":f"DEMO-{i:03d}/2026","published_at":"2026-07-08T12:00:00","proposal_end_at":end,"estimated_value":value,"url":"https://pncp.gov.br/","score":score,"matched_terms":terms,"category":cat,"status":"aberta","raw":{}}
        result.append(upsert_opportunity(item))
    return {"loaded":len(result),"items":result}
