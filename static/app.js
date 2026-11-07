/* PaperTrail frontend: no frontend API key, all PDF/AI operations handled by the server. */
const $ = (s) => document.querySelector(s);
const escapeHTML = (x) => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name, cl='') => `<svg class="icon ${cl}"><use href="#ico-${name}"></use></svg>`;
const defaultContext = '我正在研究青岛市南区公共游憩空间的供需适配与优化，希望识别居民日常需求、旅游活动与公共游憩空间服务供给的空间关系。';
const defaultGoal = '提取论文作者实际使用的评价指标、定义、数据来源和适用边界，用于搭建公共游憩空间供需评价指标体系。';
const skillFallback = [{id:'indicators',name:'指标提取',description:'评价指标、定义和数据来源'},{id:'methods',name:'方法分析',description:'数据、方法、研究步骤'},{id:'findings',name:'结论与局限',description:'主要发现、研究局限'}];
let model = {data:null,view:'workspace',busy:'',selectedDoc:'',selectedSkill:'indicators',taskInput:{context:defaultContext,goal:defaultGoal},currentTask:null,relevance:null,draft:null,workingDraft:null,selectedCard:null,reviewed:false};
let toastTimeout;

async function api(path, options={}) {
  const res = await fetch(path, {...options, credentials:'same-origin'});
  let body;
  try { body = await res.json(); } catch { body = {}; }
  if(!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败（${res.status}）`);
  return body;
}
function toast(text, error=false) {
  const el = $('#toast'); el.textContent=text; el.className='toast show'+(error?' error':'');
  clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>el.className='toast',3600);
}
function dateStr(d){try {return new Date(d).toLocaleDateString('zh-CN',{month:'short',day:'numeric',year:'numeric'});} catch{return '';}}
function skillName(id){return (model.data?.skills || skillFallback).find(x=>x.id===id)?.name || '定向阅读';}
function fileCount(){return model.data?.documents?.length||0;}
function cardCount(){return model.data?.cards?.length||0;}
function hasDemo(){return model.data?.mode!=='ai';}
async function refresh(){ model.data=await api('/api/state'); render(); }
function busy(text){model.busy=text;render();}
function done(){model.busy='';render();}
function render(){
  if(!model.data)return;
  $('#modeBadge').textContent=hasDemo()?'演示模式 · 无模型':'GPT-4.1 · 已配置';
  $('#modeBadge').className='mode-badge'+(hasDemo()?' demo':'');
  $('#docCounter').textContent=fileCount(); $('#cardCounter').textContent=cardCount();
  const names={workspace:'阅读工作台',library:'我的文献库',cards:'阅读成果卡'};
  $('#topPageName').textContent=names[model.view];
  document.querySelectorAll('.nav-link').forEach(e=>e.classList.toggle('is-active',e.dataset.view===model.view));
  $('#content').innerHTML=model.view==='workspace'?workspaceView():(model.view==='library'?libraryView():cardsView());
}
function header(title,sub,right=''){
  return `<div class="page-heading"><div><div class="overline">PAPERTRAIL / YOUR RESEARCH SPACE</div><h1>${title}</h1><p>${sub}</p></div>${right}</div>`;
}
function workspaceView(){
  const doc = model.data.documents.find(d=>d.id===model.selectedDoc);
  const count = model.draft?.entries?.length || 0;
  return `${header('每一次阅读，都更接近答案。','带着你的研究问题，让 AI 阅读、定位证据、整理成果。','<span class="tag-note">✦ Your research, beautifully organized</span>')}
  <section class="hero"><div class="hero-copy"><div class="hero-eyebrow">AI RESEARCH WORKSPACE</div><h2>不只是总结论文，<br>而是找到你真正需要的答案。</h2><p>定义阅读任务 → 识别相关性 → 定向信息提取 → 原文核查 → 保存研究卡片。一套为学术阅读设计的可控工作流。</p></div><div class="hero-art"><div class="floating-page back"></div><div class="floating-page"><div class="mini-symbol">✦</div><div class="page-line wide"></div><div class="page-line mid"></div><div class="page-line wide"></div><div class="page-line short"></div></div></div></section>
  ${model.data?.ephemeral?`<div class="mode-alert"><strong>在线演示版：</strong>云端仅使用临时存储，服务实例变化后论文和阅读卡片可能丢失。请及时导出结果；不要上传敏感或未获授权的文件。</div>`:''}
  ${hasDemo()?`<div class="mode-alert"><strong>当前是透明演示模式。</strong> PDF 上传、页码解析、片段检索、保存与导出可实际使用；不接入 GPT-4.1 时不会生成真实 AI 结论。你可先用演示论文走通流程，部署后通过服务端环境变量启用 AI。</div>`:''}
  <div class="two-columns">
    <div>
      <section class="panel panel-pad"><div class="panel-title"><h3>创建新的阅读任务</h3><span class="step-chip">01 · DEFINE</span></div>
        <div class="field"><label class="field-label" for="researchContext">研究背景 <small>让 Agent 理解你为什么读这篇论文</small></label><textarea id="researchContext" class="textbox" rows="3" placeholder="例如：我正在研究城市公共空间中的居民游憩需求...">${escapeHTML(model.taskInput.context)}</textarea></div>
        <div class="field"><label class="field-label" for="researchGoal">这次想解决的问题 <small>尽量具体</small></label><textarea id="researchGoal" class="textbox short" rows="2" placeholder="例如：提取作者实际使用的评价指标及数据来源...">${escapeHTML(model.taskInput.goal)}</textarea></div>
        <div class="field"><label class="field-label">选择阅读 Skill <small>可复用的任务规则，而非一句提示词</small></label><div class="skill-grid">${(model.data.skills||skillFallback).map((s,i)=>`<button class="skill-option ${model.selectedSkill===s.id?'selected':''}" data-skill="${s.id}"><span class="skill-num">SKILL 0${i+1}</span><strong>${escapeHTML(s.name)}</strong><span>${escapeHTML(s.description)}</span></button>`).join('')}</div></div>
        <div class="field"><label class="field-label">上传研究文献 <small>目前支持单篇 PDF，20 MB / 100 页以内</small></label><div class="upload-zone" data-action="upload"><div class="upload-icon">${icon('upload')}</div><div><strong>点击上传或拖拽 PDF 到这里</strong><span>自动解析正文、页码并建立局部检索片段</span></div></div><div class="or-divider">或者使用已经上传的文献</div><select class="select" id="docPick"><option value="">请选择文献...</option>${model.data.documents.map(d=>`<option value="${d.id}" ${d.id===model.selectedDoc?'selected':''}>${escapeHTML(d.name)} (${d.page_count}页)</option>`).join('')}</select>
        ${doc?`<div class="doc-info">${icon('file')} 已选：${escapeHTML(doc.name)} · ${doc.page_count} 页 ${doc.warnings?.length?`· ${doc.warnings.length} 条解析提示`:''}</div>`:''}
        ${doc&&doc.warnings?.length?`<div class="warning-banner">${escapeHTML(doc.warnings.slice(0,2).join('；'))}</div>`:''}</div>
        <div class="action-line"><button class="btn primary big" data-action="start" ${model.busy?'disabled':''}>${model.busy?`<span class="spinner"></span>${escapeHTML(model.busy)}`:`开始相关性判断 ${icon('arrow')}`}</button><button class="btn secondary" data-action="sample" ${model.busy?'disabled':''}>${icon('spark')} 体验示例</button></div><div class="fine-print">不会自动保存 AI 生成的结论。相关性与原文证据均需要你确认。</div>
      </section>
      ${model.busy?`<div class="analysis-area"><div class="busy-screen"><span class="spinner"></span><div><strong>${escapeHTML(model.busy)}</strong><span>正在按阅读任务处理文献，请勿重复提交。</span></div></div></div>`:''}
      ${model.relevance&&!model.busy?relevanceSection():''}
      ${model.draft&&!model.busy?draftSection():''}
    </div>
    <div><section class="panel process-card"><div class="panel-title"><h3>Agent 工作流程</h3><span class="small-caption">LIVE WORKFLOW</span></div>
      <div class="process-track">${processStep(1,'输入研究任务','明确研究背景、目标和 Skill',model.selectedDoc?'done':'active')}${processStep(2,'解析 PDF','保留原文及页码，建立检索片段',model.selectedDoc?'done':'waiting')}${processStep(3,'相关性判断','判断是否值得进入精读',model.relevance?'done':(model.busy?'active':'waiting'))}${processStep(4,'定向阅读与证据核查','按 Skill 提取并两层验证',model.draft?'done':(model.relevance?'active':'waiting'))}${processStep(5,'人工确认与成果保存','编辑、确认、保存可复用卡片',model.workingDraft?'active':'waiting')}</div>
      <hr class="divider"><div class="tiny-label">当前工作区</div><div class="stat-row"><div class="stat-item"><strong>${fileCount()}</strong><span>已上传论文</span></div><div class="stat-item"><strong>${cardCount()}</strong><span>成果卡片</span></div><div class="stat-item"><strong>${count||'—'}</strong><span>本次提取条目</span></div></div>
      <div class="quote-card"><div class="spark">✦</div><p>“让 AI 帮你找证据，而不是替你下结论。”</p><div class="method-chips"><span>来源可追溯</span><span>人工确认</span><span>结果可复用</span></div></div></section>
      ${recentTaskSection()}
    </div>
  </div>`;
}
function processStep(no,title,desc,status){return `<div class="process-step ${status}"><div class="process-dot">${status==='done'?icon('check'):String(no).padStart(2,'0')}</div><div><strong>${title}</strong><p>${desc}</p></div></div>`;}
function recentTaskSection(){
  const recent = model.data.tasks.slice(0,3);
  if(!recent.length) return `<section class="panel panel-pad" style="margin-top:17px"><div class="tiny-label">TIPS FOR BETTER RESULTS</div><p style="font-size:11px;color:#9aa2b7;line-height:2;margin:13px 0 0">例如：「提取作者真正使用的评价指标」，会比「总结这篇论文」更容易获得可检查的结果。</p></section>`;
  return `<section class="panel panel-pad" style="margin-top:17px"><div class="panel-title" style="margin-bottom:9px"><h3 style="font-size:14px">最近的阅读任务</h3></div>${recent.map(t=>`<div style="padding:11px 0;border-bottom:1px solid #f0f0f6;display:flex;gap:7px;justify-content:space-between;align-items:center"><div style="min-width:0"><div style="font-size:11px;color:#565f7e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px">${escapeHTML(t.goal)}</div><div style="font-size:10px;color:#aaafc1">${escapeHTML(skillName(t.skill))} · ${escapeHTML(t.stage)}</div></div><button class="link-btn" data-action="resume" data-id="${t.id}">继续 ↗</button></div>`).join('')}</section>`;
}
function relevanceSection(){
  const r = model.relevance;
  const isAI = r.mode==='ai';
  return `<section class="analysis-area"><div class="analysis-heading"><span class="step-chip">02 · MATCH</span><h2>文献相关性判断</h2><span class="line"></span></div>
    <div class="panel analysis-panel"><div class="verdict-head"><span class="verdict-label">${isAI?'分析完成':'演示线索已生成'}</span><span class="pill ${isAI?'':'warning'}">${escapeHTML(r.verdict)}</span></div>
    <p>${escapeHTML(r.reason)}</p><div class="info-pairs"><div class="info-pair"><small>可用内容</small><p>${escapeHTML(r.usable||'暂无')}</p></div><div class="info-pair"><small>仍需关注的缺口</small><p>${escapeHTML(r.gap||'暂无')}</p></div></div>
    ${(r.evidence||[]).map(e=>`<div class="evidence-snippet"><small>PDF 第 ${e.page} 页 · 原文片段</small>${escapeHTML(e.quote)}<br/><button class="link-btn" data-action="evidence" data-doc="${model.selectedDoc}" data-page="${e.page}" data-quote="${escapeHTML(e.quote)}">${icon('eye')} 核对原文 ↗</button></div>`).join('')}
    <div class="action-line" style="margin-top:23px"><button class="btn primary" data-action="analyze">我已确认，进入定向阅读 ${icon('arrow')}</button><button class="btn secondary" data-action="reset-task">调整任务</button></div>
    <div class="fine-print">你决定是否值得精读；系统不会因一个相关性分数自动替你继续。</div></div></section>`;
}
function draftSection(){
  const d = model.workingDraft || model.draft;
  if(!d) return '';
  const autoCount=d.entries.filter(e=>e.verification==='自动核验通过').length;
  return `<section class="analysis-area" id="draftArea"><div class="analysis-heading"><span class="step-chip">03 · EXTRACT & REVIEW</span><h2>结构化阅读卡片</h2><span class="line"></span></div>
   <div class="result-hero"><div class="overline" style="margin-bottom:12px">EDITABLE READING CARD · ${escapeHTML(skillName(d.skill))}</div><textarea aria-label="卡片标题" id="draftTitle" class="title-edit" rows="2">${escapeHTML(d.title)}</textarea><textarea aria-label="研究摘要" id="draftSummary" class="summary-edit" rows="3">${escapeHTML(d.summary)}</textarea><div class="method-chips">${(d.tags||[]).map(t=>`<span>${escapeHTML(t)}</span>`).join('')}<span>${d.entries.length} 条原文线索</span><span>${autoCount} 条自动核验</span></div></div>
   ${d.mode==='demo'?`<div class="mode-alert">${escapeHTML(d.review_warning)}</div>`:`<div class="callout" style="margin-bottom:15px">已进行逐字匹配和模型语义核验。<strong>自动核验不是人工复核</strong>，请使用每条下方的「查看 PDF 原文」。</div>`}
   ${d.entries.length?d.entries.map((e,i)=>renderEntry(e,i,d.document_id)).join(''):`<div class="panel panel-pad">未检索到可以建立证据的结论，请调整阅读目标或检查 PDF 解析质量。不要为凑条目编写无依据结论。</div>`}
   <div class="panel panel-pad" style="margin-top:17px"><div class="panel-title"><h3>你的阅读笔记</h3><span class="small-caption">仅保存在当前卡片</span></div><textarea id="draftNotes" class="note-area" placeholder="写下你对方法适用性、指标复用或后续研究的思考...">${escapeHTML(d.notes||'')}</textarea>
   <div class="review-box"><label><input type="checkbox" id="reviewCheck" ${model.reviewed?'checked':''}>我已核对引用来源，并确认卡片中的结论、AI 推断与待核查内容已合理区分。</label><p>保存代表你对成果进行过人工确认；不会改变原本的自动核查结果。</p></div>
   <div class="review-footer"><span class="fine-print">保存后可在「阅读成果卡」中导出 Markdown / JSON。</span><button class="btn primary big" data-action="save" ${model.reviewed?'':'disabled'}>${icon('check')} 确认并保存阅读卡片</button></div></div>
   </section>`;
}
function renderEntry(e,i,docId){
  const confirmed=e.verification==='自动核验通过';
  return `<article class="result-entry"><div class="entry-head"><span class="entry-category">${escapeHTML(e.category)}</span><span class="entry-confirm ${confirmed?'':'pending'}">${confirmed?'✓ 自动核验通过':'◌ '+escapeHTML(e.verification||'待核查')}</span></div>
     <textarea aria-label="条目${i+1}结论" class="entry-edit" data-entry-index="${i}" rows="2">${escapeHTML(e.claim)}</textarea>
     <div class="entry-source"><strong>ORIGINAL SOURCE · PDF P.${e.page||'?'}${e.printed_page?' / 印刷页 '+escapeHTML(e.printed_page):''}</strong>“${escapeHTML(e.quote||'未找到原文引文')}”</div>
     <div class="entry-footer"><span>${escapeHTML(e.kind||'待分类')} · ${escapeHTML(e.verification_reason||'')}</span><div><button class="link-btn" data-action="evidence" data-doc="${docId}" data-page="${e.page||1}" data-quote="${escapeHTML(e.quote||'')}">查看 PDF 原文 ↗</button><span style="padding:0 7px;color:#dadcea">|</span><button class="entry-remove" data-action="remove-entry" data-index="${i}">移除</button></div></div>
   </article>`;
}
function libraryView(){
  return `${header('把阅读过的，都留在这里。','上传并管理单篇论文，随时返回原文查看。',`<button class="btn primary" data-action="upload">${icon('upload')} 上传新文献</button>`)}
  <div class="panel panel-pad" style="margin-bottom:21px"><div class="panel-title"><h3>文献库</h3><span class="step-chip">${fileCount()} FILES</span></div><div class="small-caption" style="margin-bottom:13px">点击「用于新任务」回到工作台，可以重新以另一种研究目标阅读同一篇论文。</div>
  ${fileCount()?`<div class="page-list">${model.data.documents.map(d=>`<div class="list-card"><div class="list-main"><div class="list-icon">${icon('file')}</div><div><h3>${escapeHTML(d.name)}</h3><p>${d.page_count} 页 · ${dateStr(d.created_at)} ${d.warnings?.length?`· ${d.warnings.length} 条解析提示`:''}</p></div></div><div class="list-actions"><button class="btn secondary" data-action="open-doc" data-doc="${d.id}" data-page="1">查看原文</button><button class="btn ghost" data-action="use-doc" data-id="${d.id}">用于新任务</button><button class="btn danger" data-action="delete-doc" data-id="${d.id}" title="删除文献及其关联成果">${icon('trash')}</button></div></div>`).join('')}</div>`:emptyState('还没有上传论文','先上传一篇论文，或者体验内置的演示文档','sample','体验演示论文')}
  </div><div class="callout"><strong>隐私提示：</strong>文档和卡片保存在当前服务实例中，使用匿名浏览器会话区分。它不是账号级身份认证；不要将含有隐私或未获授权的材料上传到公开演示站。可删除单篇文献或清除本会话数据。</div><div style="margin-top:20px"><button class="btn danger" data-action="wipe">删除当前会话全部数据</button></div>`;
}
function cardsView(){
  if(model.selectedCard){
    const found=model.data.cards.find(c=>c.id===model.selectedCard);
    if(found) return cardDetail(found);
    model.selectedCard=null;
  }
  return `${header('知识不是看过，而是留下。','把阅读结论变成可检索、可追溯、可复用的研究卡片。',`<span class="tag-note">${cardCount()} READING CARDS</span>`)}
  ${cardCount()?`<div class="card-list">${model.data.cards.map(c=>`<article class="saved-card" role="button" tabindex="0" data-action="open-card" data-id="${c.id}"><span class="pill neutral">${escapeHTML(skillName(c.skill))}</span><h3>${escapeHTML(c.content.title)}</h3><p>${escapeHTML(c.content.summary||'未填写摘要')}</p><div class="card-foot"><span>${escapeHTML(c.content.document_name)} · ${dateStr(c.updated_at)}</span><span>查看卡片 ${icon('chevron')}</span></div></article>`).join('')}</div>`:emptyState('还没有阅读成果','完成相关性判断、定向提取并确认保存后，成果会出现这里。','to-workspace','创建阅读任务')}`;
}
function cardDetail(c){
  const d=c.content;
  return `<div class="detail-top"><button class="detail-back" data-action="back-cards">← 返回成果卡列表</button><span class="overline">/ SAVED READING CARD</span></div>
  <section class="detail-header"><div class="overline">CONFIRMED CARD · ${escapeHTML(skillName(d.skill))}</div><h1>${escapeHTML(d.title)}</h1><p>${escapeHTML(d.summary)}</p><div class="tags">${(d.tags||[]).map(t=>`<span class="tag">${escapeHTML(t)}</span>`).join('')}<span class="tag">已人工确认</span>${d.mode==='demo'?'<span class="tag" style="background:#fff1e2;color:#a9763d">演示生成</span>':''}</div></section>
  <div class="detail-actions"><button class="btn primary" data-action="export-markdown" data-id="${c.id}">${icon('download')} 导出 Markdown</button><button class="btn secondary" data-action="export-json" data-id="${c.id}">${icon('download')} 导出 JSON</button><button class="btn secondary" data-action="open-doc" data-doc="${d.document_id}" data-page="1">查看整篇论文</button><button class="btn danger" data-action="delete-card" data-id="${c.id}">${icon('trash')} 删除卡片</button></div>
  <div class="two-columns"><div class="panel panel-pad"><div class="panel-title"><h3>文献提取成果</h3><span class="step-chip">${d.entries.length} ENTRIES</span></div>
  ${(d.entries||[]).map((e,i)=>`<article class="detail-entry"><div class="entry-head"><span class="entry-category">${escapeHTML(e.category)}</span><span class="entry-confirm ${e.verification==='自动核验通过'?'':'pending'}">${escapeHTML(e.verification||'待核查')}</span></div><h3>${escapeHTML(e.claim)}</h3><div class="detail-quote">“${escapeHTML(e.quote)}”</div><div class="entry-footer"><span>${escapeHTML(e.kind)} · PDF 第 ${e.page||'?'} 页</span><button class="link-btn" data-action="evidence" data-doc="${d.document_id}" data-page="${e.page||1}" data-quote="${escapeHTML(e.quote)}">检查原文 ↗</button></div></article>${i<d.entries.length-1?'<hr class="divider"/>':''}`).join('')}
  </div><aside><div class="panel panel-pad"><div class="tiny-label">RESEARCH QUESTION</div><p style="font-size:12px;color:#68748d;line-height:2;margin:12px 0 0">${escapeHTML(d.goal)}</p><hr class="divider"/><div class="tiny-label">关联文献</div><p style="font-size:11px;color:#8f97ac;margin-top:9px">${escapeHTML(d.document_name)}</p><hr class="divider"/><div class="tiny-label">我的阅读笔记</div><p class="detail-notes">${escapeHTML(d.notes||'（无额外笔记）')}</p></div><div class="callout">${d.mode==='demo'?'这是没有连接 GPT-4.1 时的演示成果。':'自动核验仅是辅助，'}保存代表用户执行了人工确认。请勿将待核查的 AI 结论直接当作学术证据。</div></aside></div>`;
}
function emptyState(title,desc,action,btnText){return `<div class="empty-state"><div class="empty-symbol">${icon('books')}</div><strong>${title}</strong><p>${desc}</p><button class="btn primary" data-action="${action}">${btnText} ${icon('arrow')}</button></div>`;}

function navigate(view){model.view=view;model.selectedCard=null;render();window.scrollTo({top:0,behavior:'smooth'});}
async function uploadFile(file){
  if(!file)return;
  if(!file.name.toLowerCase().endsWith('.pdf')){toast('请选择 PDF 文件',true);return;}
  if(file.size>20*1024*1024){toast('文件不能超过 20 MB',true);return;}
  try{
    busy('正在解析论文与建立检索片段');
    const form=new FormData();form.append('file',file);
    const result=await api('/api/documents/upload',{method:'POST',body:form});
    model.selectedDoc=result.id; model.currentTask=null; model.relevance=null;model.draft=null;model.workingDraft=null;model.reviewed=false;
    await refresh();toast(`上传成功：${result.page_count} 页，已建立 ${result.chunk_count} 个检索片段`);
  }catch(err){toast(err.message,true);}finally{done();}
}
async function loadDemo(){
  try{
    busy('正在导入演示论文');
    const doc=await api('/api/sample',{method:'POST'});
    model.selectedDoc=doc.id; model.currentTask=null;model.relevance=null;model.draft=null;model.workingDraft=null;model.reviewed=false;
    model.taskInput={context:defaultContext,goal:defaultGoal};model.selectedSkill='indicators'; model.view='workspace';
    await refresh();toast('已导入原创演示论文，可开始相关性判断');
    // Let the user explicitly start each phase of the workflow.
  }catch(err){toast(err.message,true);}finally{done();}
}
async function runRelevance(){
  const context=model.taskInput.context.trim(),goal=model.taskInput.goal.trim();
  if(!model.selectedDoc){toast('请先上传或选择 PDF 文献',true);return;}
  if(context.length<4||goal.length<4){toast('请补充研究背景和阅读目标',true);return;}
  try{
    busy('Agent 正在判断任务相关性');
    const out=await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({document_id:model.selectedDoc,context,goal,skill:model.selectedSkill})});
    model.currentTask=out.id;model.relevance=out.relevance;model.draft=null;model.workingDraft=null;model.reviewed=false;
    await refresh();toast('相关性判断已完成，请确认是否进入精读');
  }catch(err){toast(err.message,true);}finally{done();}
}
async function runAnalyze(){
  if(!model.currentTask){toast('请先创建阅读任务',true);return;}
  try{
    busy('Agent 正在按 Skill 提取并核验原文证据');
    const out=await api(`/api/tasks/${model.currentTask}/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed_relevance:true})});
    model.draft=out.draft;
    model.workingDraft=JSON.parse(JSON.stringify({...out.draft,notes:''}));model.reviewed=false;
    await refresh();toast(`${out.draft.entries.length} 条原文线索已整理，请逐条核查并保存`);
    setTimeout(()=>$('#draftArea')?.scrollIntoView({behavior:'smooth',block:'start'}),80);
  }catch(err){toast(err.message,true);}finally{done();}
}
async function resumeTask(id){
  try{
    busy('正在恢复阅读任务');const t=await api(`/api/tasks/${id}`);
    model.view='workspace';model.selectedDoc=t.document_id;model.selectedSkill=t.skill;model.taskInput={context:t.context,goal:t.goal};
    model.currentTask=t.id;model.relevance=t.relevance;model.draft=t.draft;
    model.workingDraft=t.draft?JSON.parse(JSON.stringify({...t.draft,notes:''})):null;model.reviewed=false;
    render();toast('已恢复阅读任务');
  }catch(err){toast(err.message,true);}finally{done();}
}
async function saveCard(){
  if(!model.reviewed){toast('请先勾选人工核查确认',true);return;}
  const d=model.workingDraft;
  if(!d||!model.currentTask)return;
  if(!d.title.trim()){toast('请填写卡片标题',true);return;}
  const payload={confirmed:true,title:d.title.trim(),summary:d.summary||'',tags:d.tags||[],entries:d.entries||[],notes:d.notes||''};
  try{
    busy('正在保存经确认的成果卡片');
    const saved=await api(`/api/tasks/${model.currentTask}/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    model.selectedCard=saved.id;model.view='cards';model.relevance=null;model.draft=null;model.workingDraft=null;
    await refresh();toast('阅读卡片已保存，可导出 Markdown / JSON');window.scrollTo({top:0,behavior:'smooth'});
  }catch(err){toast(err.message,true);}finally{done();}
}
function showEvidence(doc,page,quote=''){
  if(!doc){toast('找不到关联原文',true);return;}
  const validPage=Math.max(1,Number(page)||1);
  const url=`/api/documents/${encodeURIComponent(doc)}/file#page=${validPage}&view=FitH`;
  $('#pdfFrame').src=url;$('#sourceMeta').textContent=`PDF 第 ${validPage} 页`;
  $('#sourceQuote').textContent=quote || '请浏览原文确认论文的完整上下文。';
  $('#openPdfTab').href=url;$('#evidenceModal').classList.remove('hidden');
}
function closeEvidence(){$('#evidenceModal').classList.add('hidden');$('#pdfFrame').src='about:blank';}
function downloadFile(name,contents,type){
  const blob = new Blob([contents],{type});const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),900);
}
function fileSafe(title){return title.replace(/[\\/:*?"<>|]/g,'_').slice(0,58)||'阅读卡片';}
function toMarkdown(c){
  const d=c.content;
  const lines=[`# ${d.title}`,'',`- 关联文献：${d.document_name}`,`- 阅读目标：${d.goal}`,`- 阅读 Skill：${skillName(d.skill)}`,`- 人工确认：${d.reviewed_by_user?'是':'否'}`,`- 分析模式：${d.mode==='ai'?'GPT-4.1':'本地演示'}`,'', '## 研究任务视角摘要','',d.summary,'','## 定向提取条目',''];
  for(const e of d.entries){lines.push(`### ${e.category}`,'',e.claim,'',`- 信息性质：${e.kind}` ,`- 证据状态：${e.verification}`,`- PDF 页码：${e.page||'未定位'}`,`- 论文印刷页码：${e.printed_page||'未识别'}`,`- 原文引文：> ${e.quote}`,`- 核查说明：${e.verification_reason}`,'');}
  lines.push('## 我的阅读笔记','',d.notes||'（无）','', '> 注：演示输出及 AI 结果请结合原文复核。');
  return lines.join('\n');
}
function openAbout(){
  const msg='PaperTrail 阅读流程\n\n① 上传单篇 PDF、保留 PDF 页码与原文索引。\n② 输入研究背景与目标，先判断任务相关性。\n③ 选择指标、方法或结论 Skill 定向提取。\n④ 核查引用确实存在、语义是否支持结论。\n⑤ 用户在原文阅读器复核并编辑后保存卡片。\n\nGPT-4.1 通过服务端 OPENAI_API_KEY 接入；未配置时只提供明确标注的规则演示，不伪装 AI 结果。';
  window.alert(msg);
}

// Global events remain attached even when views are re-rendered.
document.addEventListener('click',async ev=>{
  const nav=ev.target.closest('[data-view]');if(nav){navigate(nav.dataset.view);return;}
  const skill=ev.target.closest('[data-skill]');if(skill){model.selectedSkill=skill.dataset.skill;render();return;}
  const b=ev.target.closest('[data-action]');if(!b)return;
  const action=b.dataset.action;
  switch(action){
    case 'upload':$('#uploadInput').click();break;
    case 'sample':await loadDemo();break;
    case 'start':await runRelevance();break;
    case 'analyze':await runAnalyze();break;
    case 'save':await saveCard();break;
    case 'reset-task':model.relevance=null;model.draft=null;model.workingDraft=null;model.reviewed=false;render();break;
    case 'to-workspace':navigate('workspace');break;
    case 'resume':await resumeTask(b.dataset.id);break;
    case 'show-about':openAbout();break;
    case 'close-modal':closeEvidence();break;
    case 'evidence':case 'open-doc':showEvidence(b.dataset.doc,b.dataset.page,b.dataset.quote);break;
    case 'use-doc':model.selectedDoc=b.dataset.id;model.relevance=null;model.draft=null;model.workingDraft=null;navigate('workspace');toast('已选择文献，请设置阅读目标');break;
    case 'remove-entry': {
      const idx=Number(b.dataset.index);
      if(model.workingDraft&&Number.isInteger(idx)){model.workingDraft.entries.splice(idx,1);render();}
      break;
    }
    case 'open-card':model.selectedCard=b.dataset.id;render();window.scrollTo({top:0,behavior:'smooth'});break;
    case 'back-cards':model.selectedCard=null;render();break;
    case 'export-json':case 'export-markdown':{
      const c=model.data.cards.find(x=>x.id===b.dataset.id);if(!c)return;
      if(action==='export-json')downloadFile(`${fileSafe(c.content.title)}.json`,JSON.stringify(c.content,null,2),'application/json;charset=utf-8');
      else downloadFile(`${fileSafe(c.content.title)}.md`,toMarkdown(c),'text/markdown;charset=utf-8');
      toast('文件已导出');break;
    }
    case 'delete-doc':{
      const d=model.data.documents.find(x=>x.id===b.dataset.id);
      if(!window.confirm(`确认删除「${d?.name||'该文献'}」及其全部关联任务、卡片吗？此操作无法撤销。`))return;
      try{await api(`/api/documents/${b.dataset.id}`,{method:'DELETE'});if(model.selectedDoc===b.dataset.id)model.selectedDoc='';model.relevance=null;model.draft=null;model.workingDraft=null;await refresh();toast('文献及关联成果已删除');}catch(err){toast(err.message,true);}break;
    }
    case 'delete-card':{
      if(!window.confirm('确认删除这张阅读卡片吗？'))return;
      try{await api(`/api/cards/${b.dataset.id}`,{method:'DELETE'});model.selectedCard=null;await refresh();toast('卡片已删除');}catch(err){toast(err.message,true);}break;
    }
    case 'wipe':{
      if(!window.confirm('确认删除这个浏览器会话的所有论文、任务、卡片和事件数据？'))return;
      try{await api('/api/my-data',{method:'DELETE'});model.selectedDoc='';model.currentTask=null;model.relevance=null;model.draft=null;model.workingDraft=null;await refresh();toast('已删除本会话数据');}catch(err){toast(err.message,true);}break;
    }
  }
});
document.addEventListener('change',ev=>{
  if(ev.target.id==='uploadInput'){uploadFile(ev.target.files[0]);ev.target.value='';}
  if(ev.target.id==='docPick'){model.selectedDoc=ev.target.value;model.relevance=null;model.draft=null;model.workingDraft=null;model.reviewed=false;render();}
  if(ev.target.id==='reviewCheck'){model.reviewed=ev.target.checked;const save=document.querySelector('[data-action="save"]');if(save)save.disabled=!model.reviewed;}
});
document.addEventListener('input',ev=>{
  if(ev.target.id==='researchContext')model.taskInput.context=ev.target.value;
  if(ev.target.id==='researchGoal')model.taskInput.goal=ev.target.value;
  const d=model.workingDraft;if(!d)return;
  if(ev.target.id==='draftTitle')d.title=ev.target.value;
  if(ev.target.id==='draftSummary')d.summary=ev.target.value;
  if(ev.target.id==='draftNotes')d.notes=ev.target.value;
  if(ev.target.dataset.entryIndex!==undefined){
    const index=Number(ev.target.dataset.entryIndex), entry=d.entries[index];
    if(entry){
      if(entry.claim!==ev.target.value && entry.verification==='自动核验通过'){
        entry.verification='编辑后待核查';
        entry.verification_reason='结论已编辑，原自动语义核验不再适用。';
        const flag=ev.target.closest('.result-entry')?.querySelector('.entry-confirm');
        if(flag){flag.classList.add('pending');flag.textContent='◌ 编辑后待核查';}
      }
      entry.claim=ev.target.value;
    }
  }
});
const content=$('#content');
content.addEventListener('dragover',ev=>{const zone=ev.target.closest('.upload-zone');if(!zone)return;ev.preventDefault();zone.classList.add('drag-over');});
content.addEventListener('dragleave',ev=>{const zone=ev.target.closest('.upload-zone');if(zone)zone.classList.remove('drag-over');});
content.addEventListener('drop',ev=>{const zone=ev.target.closest('.upload-zone');if(!zone)return;ev.preventDefault();zone.classList.remove('drag-over');uploadFile(ev.dataTransfer.files[0]);});
document.addEventListener('keydown',ev=>{if(ev.key==='Escape')closeEvidence();if((ev.key==='Enter'||ev.key===' ')&&ev.target.matches('.saved-card[role="button"]')){ev.preventDefault();ev.target.click();}});
$('#evidenceModal').addEventListener('click',ev=>{if(ev.target.id==='evidenceModal')closeEvidence();});
refresh().catch(err=>{$('#content').innerHTML=`<div class="empty-state"><strong>无法连接到应用服务</strong><p>${escapeHTML(err.message)}。请从 README 的启动命令访问网页，不要直接双击 HTML 文件。</p></div>`;});
