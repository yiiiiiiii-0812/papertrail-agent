"""Versioned, inspectable reading skills. These are task rules, not generic chat prompts."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ReadingSkill:
    id: str
    name: str
    description: str
    question: str
    fields: tuple[str, ...]
    rules: str
    keywords: tuple[str, ...]

SKILLS: dict[str, ReadingSkill] = {
    "indicators": ReadingSkill(
        id="indicators", name="指标提取", description="识别作者实际使用的评价指标、定义、计算与数据来源",
        question="作者真正使用了哪些指标？如何定义、量化，它们对应什么数据？",
        fields=("指标名称", "定义或计算", "数据来源", "适用条件"),
        rules=(
            "仅提取论文中确实用于研究设计、结果分析或构建指标体系的指标。"
            "严格区分【作者实际使用】与【文献综述仅提到】。"
            "如果缺少定义、计算方式或数据来源，应写'原文未说明'，不要推测公式。"
            "每条指标必须给出与指标直接相关的逐字原文引文。"
        ),
        keywords=("指标", "评价", "变量", "权重", "测度", "measure", "index", "indicator", "variable", "evaluation"),
    ),
    "methods": ReadingSkill(
        id="methods", name="方法分析", description="拆解研究设计、样本、数据、分析步骤及方法限制",
        question="作者如何研究这个问题？方法在什么场景下可复用？",
        fields=("研究方法", "数据与样本", "实施步骤", "适用边界"),
        rules=(
            "区分研究采用的方法和仅作背景介绍的方法。"
            "保留数据时间、样本规模、分析单位等方法条件；未见即写'原文未说明'。"
            "对方法优缺点的评价必须标注为AI推断而非作者原话。"
        ),
        keywords=("方法", "数据", "样本", "研究设计", "问卷", "访谈", "method", "sample", "data", "regression", "GIS"),
    ),
    "findings": ReadingSkill(
        id="findings", name="结论与局限", description="提取主要发现、作者明示的局限与后续研究建议",
        question="这篇论文证明或发现了什么？作者承认哪些限制？",
        fields=("主要发现", "证据类型", "作者明示的局限", "可迁移启示"),
        rules=(
            "严格区分实证结论、讨论中的推测和建议。"
            "只有作者明确指出的局限，才标为'作者局限'；AI发现的问题标为'AI推断'。"
            "不得把相关关系写成因果关系。"
        ),
        keywords=("结果", "发现", "讨论", "结论", "局限", "未来", "results", "findings", "limitations", "conclusions"),
    ),
}

TASK_CLARIFICATION_RULES = """任务澄清 Skill v1
- 从研究背景与阅读目标提取该次阅读要回答的问题；不要替用户发明新的研究目标。
- 若目标过于模糊或缺少必要范围，在相关性结果中明确提示不足与可补充项。
- 用户原输入保留不变；系统仅辅助判断、不能代替用户确认研究任务。
"""

RELEVANCE_RULES = """任务相关性判断 Skill v1
- 阅读任务优先于论文题目相似度；同领域但不能回答用户问题，应是部分相关或弱相关。
- 给出一句结论、理由、可用内容与缺口。
- 所有引用必须来自附带 chunk_id 的真实原文块，不得杜撰论文信息。
- 不足以判断时明确写'信息不足'。"""

EVIDENCE_RULES = """证据核查 Skill v1
- 第一道门槛：引文逐字存在于上传文档对应片段（容许排版空白差异）。
- 第二道门槛：引文语义上确实支持对应论断，不能只出现同一个关键词。
- 区分原文事实、作者观点与 AI 推断；没有直接证据则标'待核查'。
- 核查只是程序和模型辅助，保存前必须经用户人工确认。"""

CARD_RULES = """卡片整理 Skill v1
- 输出仅基于本篇论文，按任务保留可检索的分类字段。
- 摘要必须反映当前研究问题；证据与结论可分别编辑。
- 保存需要用户显式确认，未确认成果为草稿。
- 关联文献、PDF页码与可能的印刷页码。"""
