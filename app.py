"""PaperTrail: task-oriented, source-checkable academic reading Agent MVP."""
from __future__ import annotations

import os
import re
import json
import time
import uuid
import sqlite3
import secrets
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import parse_pdf, judge_relevance, extract_card, ai_available, MODEL
from skills import SKILLS

BASE = Path(__file__).resolve().parent
IS_VERCEL = bool(os.getenv("VERCEL"))
# On Vercel, only /tmp is writable. Data stored there is temporary and can
# disappear when serverless functions restart or route to another instance.
DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/papertrail-data" if IS_VERCEL else str(BASE / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
DB_FILE = DATA_DIR / "papertrail.sqlite3"
# Vercel Functions have a 4.5 MB request body limit; allow multipart headroom.
UPLOAD_LIMIT = (4 if IS_VERCEL else 20) * 1024 * 1024
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PaperTrail | 文献阅读 Agent", version="0.1.0", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=str(BASE / "assets")), name="assets")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, session TEXT NOT NULL, name TEXT NOT NULL,
              file_path TEXT NOT NULL, page_count INTEGER NOT NULL,
              pages_json TEXT NOT NULL, chunks_json TEXT NOT NULL,
              warnings_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_documents_session ON documents(session);
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, session TEXT NOT NULL, document_id TEXT NOT NULL,
              context TEXT NOT NULL, goal TEXT NOT NULL, skill TEXT NOT NULL,
              relevance_json TEXT NOT NULL, draft_json TEXT,
              stage TEXT NOT NULL, created_at TEXT NOT NULL,
              FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_tasks_session ON tasks(session);
            CREATE TABLE IF NOT EXISTS cards (
              id TEXT PRIMARY KEY, session TEXT NOT NULL, task_id TEXT NOT NULL UNIQUE,
              content_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_cards_session ON cards(session);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL,
              event TEXT NOT NULL, duration_ms INTEGER, created_at TEXT NOT NULL
            );
        """)

init_db()


@app.middleware("http")
async def assign_anonymous_session(request: Request, call_next):
    token = request.cookies.get("pt_session", "")
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        token = secrets.token_hex(32)
        fresh = True
    else:
        fresh = False
    request.state.owner = hashlib.sha256(token.encode()).hexdigest()
    response = await call_next(request)
    if fresh:
        response.set_cookie("pt_session", token, httponly=True, samesite="lax",
                            secure=os.getenv("COOKIE_SECURE", "true" if IS_VERCEL else "false").lower() == "true",
                            max_age=60*60*24*30, path="/")
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "public, max-age=60"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def owner(req: Request) -> str:
    return req.state.owner


def record_event(sess: str, name: str, elapsed: int | None = None) -> None:
    with db() as c:
        c.execute("INSERT INTO events(session,event,duration_ms,created_at) VALUES(?,?,?,?)",
                  (sess,name,elapsed,now()))


def document_for(req: Request, doc_id: str) -> dict:
    with db() as c:
        row = c.execute("SELECT * FROM documents WHERE id=? AND session=?", (doc_id,owner(req))).fetchone()
    if not row:
        raise HTTPException(404,"找不到文献，请检查是否已删除")
    result = dict(row)
    result["pages"] = json.loads(result.pop("pages_json"))
    result["chunks"] = json.loads(result.pop("chunks_json"))
    result["warnings"] = json.loads(result.pop("warnings_json"))
    return result


def task_for(req: Request, task_id: str) -> dict:
    with db() as c:
        row = c.execute("SELECT * FROM tasks WHERE id=? AND session=?", (task_id,owner(req))).fetchone()
    if not row:
        raise HTTPException(404,"找不到该阅读任务")
    return dict(row)


class TaskInput(BaseModel):
    document_id: str
    context: str = Field(min_length=4, max_length=2000)
    goal: str = Field(min_length=4, max_length=1500)
    skill: str = "indicators"

class AnalyzeInput(BaseModel):
    confirmed_relevance: bool = False

class SaveInput(BaseModel):
    confirmed: bool = False
    title: str = Field(min_length=2,max_length=200)
    summary: str = Field(max_length=1500)
    tags: list[str] = Field(default_factory=list,max_length=12)
    entries: list[dict[str,Any]] = Field(default_factory=list,max_length=30)
    notes: str = Field(default="", max_length=6000)


@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"ok":True, "version":"0.1.0", "mode":"ai" if ai_available() else "demo", "model":MODEL, "ephemeral":IS_VERCEL}


@app.get("/api/state")
def state(req: Request):
    with db() as c:
        docs = [dict(x) for x in c.execute("SELECT id,name,page_count,warnings_json,created_at FROM documents WHERE session=? ORDER BY created_at DESC", (owner(req),))]
        tasks = [dict(x) for x in c.execute("SELECT id,document_id,goal,skill,stage,created_at FROM tasks WHERE session=? ORDER BY created_at DESC", (owner(req),))]
        cards = [dict(x) for x in c.execute("SELECT cards.id,cards.task_id,cards.content_json,cards.updated_at,tasks.document_id,tasks.skill FROM cards JOIN tasks ON cards.task_id=tasks.id WHERE cards.session=? ORDER BY cards.updated_at DESC",(owner(req),))]
    for d in docs:
        d["warnings"] = json.loads(d.pop("warnings_json"))
    for card in cards:
        card["content"] = json.loads(card.pop("content_json"))
    return {"mode":"ai" if ai_available() else "demo", "model":MODEL, "ephemeral":IS_VERCEL,
            "documents":docs, "tasks":tasks, "cards":cards,
            "skills":[{"id":s.id,"name":s.name,"description":s.description} for s in SKILLS.values()]}


async def save_uploaded_pdf(req: Request, filename: str, raw: bytes):
    if len(raw) > UPLOAD_LIMIT:
        raise HTTPException(413,f"PDF upload limit is {UPLOAD_LIMIT // (1024*1024)} MB")
    if not raw.startswith(b"%PDF"):
        raise HTTPException(400,"文件不是有效 PDF，请上传 .pdf 文件")
    if not raw:
        raise HTTPException(400,"文件为空")
    try:
        pages, chunks, warnings = parse_pdf(raw)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    doc_id = uuid.uuid4().hex
    name = Path(filename).name[:160] or "未命名文献.pdf"
    path = UPLOAD_DIR / f"{doc_id}.pdf"
    path.write_bytes(raw)
    try:
        with db() as c:
            c.execute("INSERT INTO documents(id,session,name,file_path,page_count,pages_json,chunks_json,warnings_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (doc_id,owner(req),name,str(path),len(pages),json.dumps(pages,ensure_ascii=False),
                       json.dumps(chunks,ensure_ascii=False),json.dumps(warnings,ensure_ascii=False),now()))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    record_event(owner(req), "document_uploaded")
    return {"id":doc_id,"name":name,"page_count":len(pages),"chunk_count":len(chunks),"warnings":warnings,
            "preview": [{"page":p["pdf_page"],"printed_page":p["printed_page"],"characters":len(p["text"])} for p in pages[:4]]}


@app.post("/api/documents/upload")
async def upload(req: Request, file: UploadFile = File(...)):
    return await save_uploaded_pdf(req, file.filename or "文献.pdf", await file.read(UPLOAD_LIMIT + 1))


@app.post("/api/sample")
async def load_sample(req: Request):
    source = BASE / "assets" / "demo-paper.pdf"
    return await save_uploaded_pdf(req, "演示论文_青岛滨海公共游憩空间.pdf", source.read_bytes())


@app.get("/api/documents/{doc_id}")
def get_document(req:Request, doc_id:str):
    d = document_for(req,doc_id)
    return {"id":d["id"],"name":d["name"],"page_count":d["page_count"],"warnings":d["warnings"],
            "pages":[{"pdf_page":p["pdf_page"],"printed_page":p["printed_page"],"characters":len(p["text"])} for p in d["pages"]]}


@app.get("/api/documents/{doc_id}/file")
def original_file(req:Request, doc_id:str):
    d = document_for(req,doc_id)
    return FileResponse(d["file_path"],media_type="application/pdf",filename=d["name"],content_disposition_type="inline")


@app.delete("/api/documents/{doc_id}")
def delete_document(req:Request, doc_id:str):
    d = document_for(req,doc_id)
    with db() as c:
        c.execute("DELETE FROM documents WHERE id=? AND session=?",(doc_id,owner(req)))
    Path(d["file_path"]).unlink(missing_ok=True)
    record_event(owner(req),"document_deleted")
    return {"ok":True}


@app.post("/api/tasks")
def create_task(req:Request, payload:TaskInput):
    if payload.skill not in SKILLS:
        raise HTTPException(400,"没有这个阅读 Skill")
    d = document_for(req,payload.document_id)
    started = time.monotonic()
    try:
        relevance = judge_relevance(d,payload.context,payload.goal,payload.skill)
    except RuntimeError as exc:
        raise HTTPException(502,str(exc)) from exc
    task_id = uuid.uuid4().hex
    with db() as c:
        c.execute("INSERT INTO tasks(id,session,document_id,context,goal,skill,relevance_json,stage,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (task_id,owner(req),payload.document_id,payload.context,payload.goal,payload.skill,
                   json.dumps(relevance,ensure_ascii=False),"relevance",now()))
    record_event(owner(req),"relevance_completed",int((time.monotonic()-started)*1000))
    return {"id":task_id,"stage":"relevance","relevance":relevance,"document_id":d["id"],"skill":payload.skill}


@app.get("/api/tasks/{task_id}")
def get_task(req:Request,task_id:str):
    t = task_for(req,task_id)
    t["relevance"] = json.loads(t.pop("relevance_json"))
    t["draft"] = json.loads(t.pop("draft_json")) if t["draft_json"] else None
    return t


@app.post("/api/tasks/{task_id}/analyze")
def analyze(req:Request,task_id:str,payload:AnalyzeInput):
    t = task_for(req,task_id)
    if not payload.confirmed_relevance:
        raise HTTPException(400,"请先确认相关性判断，再执行定向阅读")
    document = document_for(req,t["document_id"])
    started = time.monotonic()
    try:
        draft = extract_card(document,t["context"],t["goal"],t["skill"])
    except RuntimeError as exc:
        raise HTTPException(502,str(exc)) from exc
    draft["document_id"] = document["id"]
    draft["document_name"] = document["name"]
    draft["skill"] = t["skill"]
    draft["goal"] = t["goal"]
    with db() as c:
        c.execute("UPDATE tasks SET stage='draft',draft_json=? WHERE id=? AND session=?",
                  (json.dumps(draft,ensure_ascii=False),task_id,owner(req)))
    record_event(owner(req),"extract_completed",int((time.monotonic()-started)*1000))
    return {"task_id":task_id,"stage":"draft","draft":draft}


@app.post("/api/tasks/{task_id}/save")
def save_card(req:Request,task_id:str,payload:SaveInput):
    t = task_for(req,task_id)
    if not t["draft_json"]:
        raise HTTPException(400,"需要先完成定向阅读才能保存卡片")
    if not payload.confirmed:
        raise HTTPException(400,"请确认已经检查原文证据后再保存")
    draft = json.loads(t["draft_json"])
    # Trust server-side evidence, never let a client silently replace references
    # or keep an AI verification badge after changing its underlying claim.
    original_map = {
        (str(e.get("chunk_id")), str(e.get("quote")), str(e.get("category"))): e
        for e in draft.get("entries", [])
    }
    safe_entries = []
    for raw in payload.entries:
        if len(str(raw.get("claim", ""))) > 1000:
            raise HTTPException(400, "单条结论过长")
        key = (str(raw.get("chunk_id")), str(raw.get("quote")), str(raw.get("category")))
        original = original_map.get(key)
        if not original:
            raise HTTPException(400, "不能替换原始证据或增加未经来源核对的条目")
        new = dict(original)
        new["claim"] = str(raw.get("claim", "")).strip()
        if new["claim"] != original.get("claim") and original.get("verification") == "自动核验通过":
            new["verification"] = "编辑后待核查"
            new["verification_reason"] = "用户已修改结论，先前模型对原结论的核验不再适用。"
        safe_entries.append(new)
    content = {"title":payload.title,"summary":payload.summary,"tags":payload.tags[:12],
               "entries":safe_entries,"notes":payload.notes,"document_id":t["document_id"],
               "document_name":draft["document_name"],"goal":t["goal"],"skill":t["skill"],
               "mode":draft["mode"],"reviewed_by_user":True}
    card_id = uuid.uuid4().hex
    with db() as c:
        existing = c.execute("SELECT id,created_at FROM cards WHERE session=? AND task_id=?",(owner(req),task_id)).fetchone()
        if existing:
            card_id = existing["id"]
            c.execute("UPDATE cards SET content_json=?,updated_at=? WHERE id=?",(json.dumps(content,ensure_ascii=False),now(),card_id))
        else:
            c.execute("INSERT INTO cards(id,session,task_id,content_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                      (card_id,owner(req),task_id,json.dumps(content,ensure_ascii=False),now(),now()))
        c.execute("UPDATE tasks SET stage='saved' WHERE id=? AND session=?",(task_id,owner(req)))
    record_event(owner(req),"card_saved")
    return {"id":card_id,"content":content}


@app.get("/api/cards/{card_id}")
def get_card(req:Request,card_id:str):
    with db() as c:
        row = c.execute("SELECT * FROM cards WHERE id=? AND session=?",(card_id,owner(req))).fetchone()
    if not row:
        raise HTTPException(404,"卡片不存在")
    out = dict(row)
    out["content"] = json.loads(out.pop("content_json"))
    return out


@app.delete("/api/cards/{card_id}")
def delete_card(req:Request,card_id:str):
    with db() as c:
        row = c.execute("SELECT task_id FROM cards WHERE id=? AND session=?",(card_id,owner(req))).fetchone()
        if not row:
            raise HTTPException(404,"卡片不存在")
        c.execute("DELETE FROM cards WHERE id=? AND session=?",(card_id,owner(req)))
        c.execute("UPDATE tasks SET stage='draft' WHERE id=? AND session=?",(row["task_id"],owner(req)))
    record_event(owner(req),"card_deleted")
    return {"ok":True}


@app.get("/api/metrics")
def get_metrics(req:Request):
    with db() as c:
        rows = [dict(x) for x in c.execute("SELECT event,COUNT(*) AS total,ROUND(AVG(duration_ms),0) AS average_ms FROM events WHERE session=? GROUP BY event",(owner(req),))]
    return {"events":rows,"note":"仅当前匿名会话的真实行为记录，不代表用户规模或效果验证。"}


@app.delete("/api/my-data")
def delete_all_my_data(req:Request):
    with db() as c:
        docs = [x["file_path"] for x in c.execute("SELECT file_path FROM documents WHERE session=?",(owner(req),))]
        c.execute("DELETE FROM documents WHERE session=?",(owner(req),))
        c.execute("DELETE FROM events WHERE session=?",(owner(req),))
    for path in docs:
        Path(path).unlink(missing_ok=True)
    return {"ok":True}
