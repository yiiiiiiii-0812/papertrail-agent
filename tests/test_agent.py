"""Executable acceptance checks. No actual AI credentials or paid calls are used."""
from __future__ import annotations
import io
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import app as api_app
import engine

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_app, "DB_FILE", tmp_path / "state.sqlite3")
    monkeypatch.setattr(api_app, "UPLOAD_DIR", tmp_path / "uploads")
    api_app.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    api_app.init_db()
    monkeypatch.setattr(engine, "API_KEY", "")
    with TestClient(api_app.app) as c:
        yield c


def add_sample(client):
    response = client.post("/api/sample")
    assert response.status_code == 200, response.text
    return response.json()


def new_task(client, doc_id):
    response = client.post("/api/tasks", json={
        "document_id": doc_id,
        "context": "研究青岛市南区滨海公共空间的服务供需关系",
        "goal": "提取作者实际使用的评价指标、定义和数据来源",
        "skill": "indicators",
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_sample_extraction_page_metadata(client):
    doc = add_sample(client)
    assert doc["page_count"] == 3
    assert doc["chunk_count"] >= 3
    with api_app.db() as c:
        row = c.execute("SELECT pages_json FROM documents WHERE id=?", (doc["id"],)).fetchone()
    import json
    pages=json.loads(row["pages_json"])
    assert pages[0]["printed_page"] == "1"
    assert "供需适配研究" in pages[0]["text"]
    assert client.get(f"/api/documents/{doc['id']}/file").content.startswith(b"%PDF")


def test_full_demo_requires_human_confirmation(client):
    doc = add_sample(client)
    task = new_task(client, doc["id"])
    assert task["relevance"]["mode"] == "demo"
    assert client.post(f"/api/tasks/{task['id']}/analyze", json={"confirmed_relevance":False}).status_code == 400
    assert client.post(f"/api/tasks/{task['id']}/save", json={"confirmed":True,"title":"阅读卡片", "summary":"", "entries":[]}).status_code == 400
    response=client.post(f"/api/tasks/{task['id']}/analyze", json={"confirmed_relevance":True})
    assert response.status_code == 200, response.text
    draft=response.json()["draft"]
    assert len(draft["entries"]) == 3
    assert {e["category"] for e in draft["entries"]} == {"步行可达覆盖率","功能供给匹配度","活动时空重叠度"}
    assert all(e["verification"] == "待核查" for e in draft["entries"])
    payload={"confirmed":False, "title":draft["title"],"summary":draft["summary"], "tags":draft["tags"],"entries":draft["entries"],"notes":"我的测试笔记"}
    assert client.post(f"/api/tasks/{task['id']}/save", json=payload).status_code == 400
    payload["confirmed"]=True
    response=client.post(f"/api/tasks/{task['id']}/save",json=payload)
    assert response.status_code == 200, response.text
    saved=response.json()
    assert saved["content"]["reviewed_by_user"] is True
    assert saved["content"]["notes"] == "我的测试笔记"
    assert len(client.get("/api/state").json()["cards"]) == 1
    assert client.get(f"/api/cards/{saved['id']}").status_code == 200


def test_anonymous_sessions_are_isolated(client):
    doc=add_sample(client)
    with TestClient(api_app.app) as another:
        assert not another.get("/api/state").json()["documents"]
        assert another.get(f"/api/documents/{doc['id']}").status_code == 404
        assert another.get(f"/api/documents/{doc['id']}/file").status_code == 404
        assert another.delete(f"/api/documents/{doc['id']}").status_code == 404
    assert client.get(f"/api/documents/{doc['id']}").status_code == 200
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert not client.get("/api/state").json()["documents"]


def test_delete_all_user_data(client):
    add_sample(client)
    assert client.delete("/api/my-data").status_code == 200
    assert client.get("/api/state").json()["documents"] == []
    assert client.get("/api/metrics").json()["events"] == []


def test_invalid_pdf_rejected(client):
    response=client.post("/api/documents/upload", files={"file":("evil.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 400
    response=client.post("/api/documents/upload", files={"file":("corrupted.pdf", b"%PDF-1.4\ninvalid", "application/pdf")})
    assert response.status_code == 422


def test_literal_evidence_check():
    chunk={"id":"p1c0","page":1,"text":"作者实际使用了步行可达覆盖率。\n需要居民点和道路网络。"}
    assert engine.quote_in_chunk("作者实际使用了步行可达覆盖率。", chunk)
    assert engine.quote_in_chunk("作者实际使用了步行可达覆盖率。需要居民点", chunk)
    assert not engine.quote_in_chunk("作者使用了空间句法作为研究指标。", chunk)


def test_mock_gpt_41_two_layer_verification(client, monkeypatch):
    doc=add_sample(client)
    monkeypatch.setattr(engine, "API_KEY", "test-key-not-used")
    def fake_llm(instructions,payload,max_tokens=1000):
        if "证据审查员" in instructions:
            return {"checks":[{"index":0,"supported":True,"reason":"定义与引文内容一致"},
                              {"index":1,"supported":True,"reason":"引文真实且可支持此结论"}]}
        if "相关性判断" in instructions:
            return {"verdict":"强相关", "reason":"包含相关的指标定义", "usable":"步行可达性", "gap":"尚无真实研究数据",
                    "evidence":[{"chunk_id":"p1c0","quote":"本文以青岛市南区的滨海公共游憩空间为模拟研究对象"}]}
        return {"title":"供需评价指标阅读卡片", "summary":"用于演示模型输出", "tags":["指标体系"],"entries":[
            {"category":"步行可达覆盖率","claim":"作者给出步行可达覆盖率指标定义","kind":"原文事实","chunk_id":"p2c0",
             "quote":"指标一：步行可达覆盖率。定义为沿步行路网"},
            {"category":"无依据说法","claim":"作者证明旅游必然导致居民退出","kind":"原文事实","chunk_id":"p2c0","quote":"论文原文里并不存在这句话"},
        ]}
    monkeypatch.setattr(engine,"json_response",fake_llm)
    task = new_task(client, doc["id"])
    assert task["relevance"]["mode"] == "ai"
    assert task["relevance"]["evidence"]
    response=client.post(f"/api/tasks/{task['id']}/analyze",json={"confirmed_relevance":True})
    assert response.status_code == 200, response.text
    entries=response.json()["draft"]["entries"]
    assert entries[0]["verification"] == "自动核验通过"
    assert entries[1]["verification"] == "待核查"
    # Even if a forged client preserves the verified badge, edited claims must lose it.
    import copy
    fake_entries=copy.deepcopy(entries)
    fake_entries[0]["claim"]="用户重新撰写了不同的结论"
    save={"confirmed":True,"title":"复核卡片","summary":"测试","tags":[],"entries":fake_entries,"notes":""}
    saved=client.post(f"/api/tasks/{task['id']}/save",json=save)
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"]["entries"][0]["verification"] == "编辑后待核查"
    # The server also rejects claims with a silently replaced source quote.
    fake_entries[0]["quote"] = "伪造原文"
    bad=client.post(f"/api/tasks/{task['id']}/save",json={**save,"entries":fake_entries})
    assert bad.status_code == 400


def test_semantic_verification_failure_retains_quotes(client, monkeypatch):
    doc=add_sample(client)
    monkeypatch.setattr(engine,"API_KEY","test-key-not-used")
    def fake_llm(instructions,payload,max_tokens=1000):
        if "证据审查员" in instructions:
            raise RuntimeError("simulate failed second model call")
        if "相关性判断" in instructions:
            return {"verdict":"部分相关", "reason":"可参考", "usable":"指标", "gap":"无", "evidence":[]}
        return {"title":"测试","summary":"", "tags":[],"entries":[
            {"category":"指标","claim":"步行可达覆盖率用于研究","kind":"原文事实", "chunk_id":"p2c0",
             "quote":"指标一：步行可达覆盖率。定义为沿步行路网"}]}
    monkeypatch.setattr(engine,"json_response",fake_llm)
    task=new_task(client,doc["id"])
    res=client.post(f"/api/tasks/{task['id']}/analyze",json={"confirmed_relevance":True})
    assert res.status_code == 200
    assert res.json()["draft"]["entries"][0]["verification"] == "待核查"
    assert "核验失败" in res.json()["draft"]["review_warning"]
