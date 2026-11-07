"""PDF extraction, local chunk retrieval, single-Agent orchestration and evidence verification."""
from __future__ import annotations

import os
import re
import json
import math
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import unicodedata
from collections import Counter
from typing import Any
import fitz
import httpx
from skills import SKILLS, TASK_CLARIFICATION_RULES, RELEVANCE_RULES, EVIDENCE_RULES, CARD_RULES

load_dotenv(Path(__file__).with_name(".env"), override=False)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
MAX_PAGE_COUNT = 100
MAX_TEXT_CHARS = 680000


def ai_available() -> bool:
    return bool(API_KEY)


def parse_pdf(raw: bytes) -> tuple[list[dict], list[dict], list[str]]:
    pages: list[dict] = []
    warnings: list[str] = []
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise ValueError("无法读取这份 PDF，请检查文件是否损坏或加密") from exc
    try:
        if doc.needs_pass:
            raise ValueError("PDF 已加密，请上传可直接阅读的版本")
        if len(doc) > MAX_PAGE_COUNT:
            raise ValueError(f"目前最多支持 {MAX_PAGE_COUNT} 页，请先拆分较长的文档")
        labels = doc.get_page_labels() if hasattr(doc, "get_page_labels") else []
        for i, page in enumerate(doc):
            text = page.get_text("text", sort=True).strip()
            if len(text) < 45:
                if os.getenv("ENABLE_OCR", "false").lower() == "true":
                    try:
                        import pytesseract
                        from PIL import Image
                        import io
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                        langs = set(pytesseract.get_languages(config=""))
                        lang = "chi_sim+eng" if "chi_sim" in langs else "eng"
                        text = pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))), lang=lang).strip()
                        if len(text) < 30:
                            warnings.append(f"第 {i+1} 页 OCR 识别文字较少，需人工核对")
                    except Exception:
                        warnings.append(f"第 {i+1} 页 OCR 失败，请换可复制文本的 PDF")
                else:
                    warnings.append(f"第 {i+1} 页文字过少，可能为扫描页；可开启服务端 OCR")
            # Detect footer page numbering, but keep PDF sequence as authority.
            lines = [t.strip() for t in text.splitlines() if t.strip()]
            printed = None
            for line in (lines[-3:] + lines[:2]):
                if re.fullmatch(r"(?:[-—–]\s*)?(\d{1,4}|[ivxlcdmIVXLCDM]{1,8})(?:\s*[-—–])?", line):
                    printed = line.strip("-—– ")
                    break
            # Page labels can be encoded in PDF metadata; footer detection takes priority.
            if not printed and labels:
                pass
            pages.append({"pdf_page": i + 1, "printed_page": printed, "text": text})
            if sum(len(p["text"]) for p in pages) > MAX_TEXT_CHARS:
                raise ValueError("文本超过首版处理限制，请上传单篇篇幅较短的论文")
    finally:
        doc.close()
    if not any(len(p["text"]) > 50 for p in pages):
        raise ValueError("未检测到有效正文；这是扫描版 PDF，请开启 OCR 后重试")
    chunks = make_chunks(pages)
    if len(warnings) > 7:
        warnings = warnings[:7] + ["另有部分页面需人工检查"]
    return pages, chunks, warnings


def make_chunks(pages: list[dict], size: int = 1250, overlap: int = 170) -> list[dict]:
    chunks = []
    for p in pages:
        text = p["text"]
        if not text:
            continue
        pos, n = 0, 0
        while pos < len(text):
            end = min(pos + size, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", pos + size//2, end), text.rfind("。", pos + size//2, end))
                if boundary > pos + 500:
                    end = boundary + 1
            segment = text[pos:end].strip()
            if segment:
                chunks.append({"id": f"p{p['pdf_page']}c{n}", "page": p["pdf_page"],
                               "printed_page": p.get("printed_page"), "text": segment})
            if end >= len(text):
                break
            pos = max(pos + 1, end - overlap)
            n += 1
    return chunks


def terms(text: str) -> list[str]:
    text = text.lower()
    words = re.findall(r"[a-z][a-z\d_-]{2,}", text)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    # 2-gram Chinese indexing works without segmentation dictionaries.
    grams = [s[i:i+2] for s in chinese for i in range(len(s)-1)]
    return words + grams


def retrieve(chunks: list[dict], query: str, skill_id: str, top_k: int = 12) -> list[dict]:
    q_terms = terms(query + " " + " ".join(SKILLS.get(skill_id, SKILLS["indicators"]).keywords))
    counts = Counter(q_terms)
    scored = []
    for c in chunks:
        words = Counter(terms(c["text"]))
        score = sum(min(n, words.get(w, 0)) * (1 + math.log1p(n)) for w, n in counts.items())
        score /= math.sqrt(1 + len(c["text"]) / 850)
        if c["page"] == 1:
            score += 1.8
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    # Avoid retrieving 12 adjacent blocks while ignoring the whole article.
    taken = []
    page_counter: Counter = Counter()
    for _score, chunk in scored:
        if page_counter[chunk["page"]] >= 3:
            continue
        taken.append(chunk)
        page_counter[chunk["page"]] += 1
        if len(taken) >= top_k:
            break
    return taken


def normalize_quote(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).replace("\u00ad", "")


def quote_in_chunk(quote: str, chunk: dict) -> bool:
    needle = normalize_quote(quote)
    return len(needle) >= 9 and needle in normalize_quote(chunk["text"])


def json_response(instructions: str, payload: dict, max_tokens: int = 1700) -> dict:
    if not API_KEY:
        raise RuntimeError("尚未配置 OPENAI_API_KEY")
    req = {
        "model": MODEL,
        "instructions": instructions + "\n只输出一个严格有效的 JSON 对象，不输出 markdown 代码围栏。",
        "input": json.dumps(payload, ensure_ascii=False),
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": max_tokens,
        "store": False,
    }
    try:
        with httpx.Client(timeout=85.0) as client:
            res = client.post("https://api.openai.com/v1/responses",
                              headers={"Authorization": f"Bearer {API_KEY}", "Content-Type":"application/json"},
                              json=req)
            res.raise_for_status()
            data = res.json()
        text = "".join(
            item.get("text", "")
            for output in data.get("output", []) if output.get("type") == "message"
            for item in output.get("content", []) if item.get("type") == "output_text"
        )
        if not text.strip():
            raise RuntimeError("模型没有返回可解析的文本，请重试")
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("模型返回格式应为 JSON 对象")
        return obj
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise RuntimeError(f"模型请求失败 (HTTP {status})，请检查 API Key、额度与模型权限") from exc
    except (httpx.RequestError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("模型输出或网络异常，请稍后重试；已存储的文档不会受影响") from exc


def _best_snippet(chunk: dict, goal: str) -> str:
    pieces = [s.strip() for s in re.split(r"(?<=[。；.!?])|\n", chunk["text"]) if len(s.strip()) > 16]
    if not pieces:
        return chunk["text"][:140]
    q = set(terms(goal))
    pieces.sort(key=lambda s: (len(set(terms(s)) & q), min(len(s), 130)), reverse=True)
    return pieces[0][:160]


def judge_relevance(document: dict, context: str, goal: str, skill_id: str) -> dict:
    chunks = document["chunks"]
    selected = retrieve(chunks, context + " " + goal, skill_id, top_k=7)
    if not selected:
        return {"verdict":"信息不足", "reason":"未找到可用正文", "usable":"", "gap":"无法核对原文", "evidence":[], "mode":"demo"}
    if not ai_available():
        # Honest fallback: local keyword hints, NOT a claimed AI relevance judgment.
        paper_terms = set(terms(" ".join(p["text"][:3000] for p in document["pages"])))
        q_terms = set(terms(goal))
        overlap = len(q_terms & paper_terms) / max(1, len(q_terms))
        verdict = "可能相关" if overlap >= 0.16 else "需人工判断"
        c = selected[0]
        return {"verdict":verdict,
                "reason":"演示模式：根据阅读任务与论文片段的关键词交集生成线索，未调用 GPT-4.1，不能作为正式相关性结论。",
                "usable":"可据下方真实原文片段决定是否继续精读。",
                "gap":"缺少模型的语义相关性判断，需要人工确认。",
                "evidence":[{"chunk_id":c["id"], "page":c["page"], "quote":_best_snippet(c, goal)}],
                "mode":"demo"}
    messages = [{"chunk_id":c["id"], "pdf_page":c["page"], "text":c["text"][:1300]} for c in selected]
    result = json_response(
        "你是学术文献阅读Agent，先执行任务澄清，再执行相关性判断Skill。" + TASK_CLARIFICATION_RULES + RELEVANCE_RULES +
        "\n返回字段 verdict（强相关/部分相关/弱相关/信息不足）, reason, usable, gap, evidence（最多2项，每项chunk_id, quote原文短句）。",
        {"research_context":context, "goal":goal, "paper_title":document["name"], "snippets":messages}, max_tokens=1000)
    evidence = []
    lookup = {c["id"]:c for c in selected}
    for item in result.get("evidence", [])[:2]:
        if not isinstance(item, dict):
            continue
        chunk = lookup.get(str(item.get("chunk_id", "")))
        quote = str(item.get("quote", ""))[:240]
        if chunk and quote_in_chunk(quote, chunk):
            evidence.append({"chunk_id":chunk["id"], "page":chunk["page"], "quote":quote})
    return {"verdict":str(result.get("verdict", "信息不足"))[:15],
            "reason":str(result.get("reason", ""))[:700], "usable":str(result.get("usable", ""))[:550],
            "gap":str(result.get("gap", ""))[:550], "evidence":evidence, "mode":"ai"}


def _demo_extract(document: dict, context: str, goal: str, skill_id: str, selected: list[dict]) -> dict:
    """Helpful local pattern demonstration; does not pretend to be generative AI."""
    skill = SKILLS[skill_id]
    entries = []
    rule_patterns = {
        "indicators": [
            ("评价指标", r"指标[一二三四五六七八九十\d]+[：:]\s*[^。\n]{2,80}。[^。]{0,125}。"),
            ("评价指标", r"指标[一二三四五六七八九十\d]+[：:]\s*[^。\n]{2,80}。"),
        ],
        "methods": [
            ("数据来源", r"3\.1\s*数据来源[。\s]*[^。]{20,220}。"),
            ("研究方法", r"3\.2\s*研究方法[。\s]*[^。]{20,240}。"),
            ("研究方法", r"首先[，,][^。]{20,180}。"),
        ],
        "findings": [
            ("研究局限", r"作者明确指出以下局限[：:][^。]{20,220}。"),
            ("研究发现", r"活动时空重叠并不必然意味着[^。]{10,180}。"),
            ("可迁移启示", r"在空间优化层面[，,][^。]{20,200}。"),
        ],
    }
    # Search the actual source, never inject a generic conclusion for unrelated PDFs.
    seen = set()
    for category, pattern in rule_patterns[skill_id]:
        for c in document["chunks"]:
            for hit in re.finditer(pattern, c["text"], flags=re.S):
                quote = hit.group(0).strip()[:240]
                if len(normalize_quote(quote)) < 10 or not quote_in_chunk(quote, c):
                    continue
                # Deduplicate a long excerpt and its shorter fallback match by heading.
                compact = re.sub(r"\s+", "", quote)
                fragments = compact.split("。")
                first = fragments[0]
                fingerprint = hashlib.sha256(first.encode()).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                # Expose an actual rule-extracted definition, still flagged for human verification.
                extracted_name = first.split("：",1)[-1] if skill_id == "indicators" else category
                second = fragments[1] if len(fragments)>1 else ""
                description = (second+"。") if (second.startswith("定义为") or second.startswith("通过")) else ""
                claim = (extracted_name+"："+description if description else first+"。") + "（原文线索，待人工核对）"
                entries.append({"category":extracted_name, "claim":claim,
                    "kind":"原文线索", "chunk_id":c["id"], "quote":quote,
                    "page":c["page"], "printed_page":c.get("printed_page"),
                    "verification":"待核查", "verification_reason":"本地正则规则匹配，已定位真实原文；未执行模型语义核验。"})
                if len(entries) >= 6:break
            if len(entries)>=6:break
        if len(entries)>=6:break
    # Fallback: independent raw text excerpts, not invented claims.
    if not entries:
        for idx,c in enumerate(selected[:4]):
            quote = _best_snippet(c, goal + " " + skill.question)
            if len(normalize_quote(quote)) < 9:
                continue
            entries.append({"category":skill.fields[min(idx,len(skill.fields)-1)],
                            "claim":quote.replace("\n"," ") + "（原文线索，待人工提炼）",
                            "kind":"原文线索", "chunk_id":c["id"], "quote":quote,
                            "page":c["page"], "printed_page":c.get("printed_page"), "verification":"待核查",
                            "verification_reason":"本地关键词检索结果，未调用 GPT-4.1 或语义核验。"})
    return {"title":document["name"].rsplit(".",1)[0],
            "summary":f"本地演示：依据「{skill.name}」规则从真实 PDF 定位到 {len(entries)} 个文本片段，形成可编辑草稿；正式的任务理解、观点归纳和双层语义核验需连接 GPT-4.1。",
            "tags":[skill.name, "原文定位演示"], "entries":entries, "mode":"demo",
            "review_warning":"当前未配置 API Key；本页为规则匹配的原文线索，不是 GPT-4.1 生成或语义核验的学术结论。"}


def _validate_excerpts(entries: list[dict], chunks: list[dict]) -> list[dict]:
    lookup = {c["id"]: c for c in chunks}
    cleaned = []
    for raw in entries[:12]:
        if not isinstance(raw, dict):
            continue
        chunk = lookup.get(str(raw.get("chunk_id", "")))
        quote = str(raw.get("quote", "")).strip()[:350]
        quote_ok = bool(chunk and quote_in_chunk(quote, chunk))
        cleaned.append({"category":str(raw.get("category", "未分类"))[:80],
                        "claim":str(raw.get("claim", ""))[:650],
                        "kind":str(raw.get("kind", "AI推断"))[:30],
                        "chunk_id":chunk["id"] if chunk else None,
                        "quote":quote,
                        "page":chunk["page"] if chunk else None,
                        "printed_page":chunk.get("printed_page") if chunk else None,
                        "verification":"语义待核查" if quote_ok else "待核查",
                        "verification_reason":"引文已在原文中找到，待语义支持核查" if quote_ok else "引用内容未在指定原文片段中找到"})
    return cleaned


def _semantic_check(entries: list[dict]) -> None:
    valid = [i for i,e in enumerate(entries) if e["verification"] == "语义待核查"]
    if not valid:
        return
    payload = [{"index":i,"claim":entries[i]["claim"],"quote":entries[i]["quote"],"kind":entries[i]["kind"]} for i in valid]
    result = json_response(
        "你是严格的学术证据审查员。"+EVIDENCE_RULES+
        "\n对每条给出是否由单独引文确实支持，不用外部常识补全信息。"
        "返回JSON对象 {\"checks\":[{\"index\":整数,\"supported\":布尔,\"reason\":简短中文原因}]}。",
        {"checks_to_make":payload}, max_tokens=1400)
    checks = {int(x["index"]):x for x in result.get("checks",[]) if isinstance(x,dict) and str(x.get("index", "")).isdigit()}
    for i in valid:
        verdict = checks.get(i)
        if verdict and verdict.get("supported") is True:
            entries[i]["verification"] = "自动核验通过"
        else:
            entries[i]["verification"] = "待核查"
        entries[i]["verification_reason"] = str((verdict or {}).get("reason", "模型未返回证据支持判断"))[:240]


def extract_card(document: dict, context: str, goal: str, skill_id: str) -> dict:
    skill = SKILLS[skill_id]
    selected = retrieve(document["chunks"], context + " " + goal, skill_id, top_k=14)
    if not ai_available():
        return _demo_extract(document, context, goal, skill_id, selected)
    snippets = [{"chunk_id":c["id"], "pdf_page":c["page"], "printed_page":c.get("printed_page"),
                 "text":c["text"]} for c in selected]
    result = json_response(
        "你是单文献阅读Agent，正在执行「"+skill.name+"」Skill。\n"+
        "执行规则："+skill.rules+"\n必须遵守：只用给出的论文原文，不使用外部常识补充论文事实。"
        "只列有依据的信息，不要凑数量。每条 claim 仅表达引文直接支持的一项事实。"
        "quote 必须是某一 chunk_id 对应文本中连续、逐字摘录的一小段（最长180字），不可自己改写、不可加省略号。"
        "kind 只能是 原文事实 / 作者观点 / AI推断；缺少依据的条目不要加入。"
        "卡片规则："+ CARD_RULES + "\n返回JSON对象字段 title（卡片标题）, summary（研究任务视角摘要，不超过160字）, tags（短字符串数组）,"
        "entries（最多10条对象数组，每条 category,claim,kind,chunk_id,quote）。",
        {"paper_title":document["name"], "research_context":context, "reading_goal":goal,
         "skill":{"name":skill.name,"question":skill.question,"output_fields":skill.fields}, "snippets":snippets},
        max_tokens=3200)
    raw_entries = result.get("entries", [])
    if not isinstance(raw_entries, list):
        raw_entries = []
    entries = _validate_excerpts(raw_entries, document["chunks"])
    review_warning = "AI自动核验仅供参考，保存前请逐条核查原文。"
    try:
        _semantic_check(entries)
    except RuntimeError:
        for e in entries:
            if e["verification"] == "语义待核查":
                e["verification"] = "待核查"
                e["verification_reason"] = "语义核验服务暂不可用，但逐字原文定位有效，请人工复核。"
        review_warning = "语义核验失败，已保留可用原文片段。请人工核对，不将其当成自动核验通过。"
    raw_tags = result.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []
    return {"title":str(result.get("title", "阅读卡片"))[:180],
            "summary":str(result.get("summary", ""))[:900],
            "tags":[str(t)[:30] for t in raw_tags[:6] if isinstance(t,str)],
            "entries":entries, "mode":"ai", "review_warning":review_warning}
