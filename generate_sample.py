"""Produce an original, explicitly fictional test paper. Not an academic source."""
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.units import mm

out = Path(__file__).resolve().parent / "assets" / "demo-paper.pdf"
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
styles = {
    "title": ParagraphStyle("T", fontName="STSong-Light", fontSize=17, leading=26, spaceAfter=12, alignment=TA_CENTER),
    "heading": ParagraphStyle("H", fontName="STSong-Light", fontSize=13, leading=23, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor("#1f3965")),
    "text": ParagraphStyle("Body", fontName="STSong-Light", fontSize=10.4, leading=20, spaceAfter=8),
    "small": ParagraphStyle("S", fontName="STSong-Light", fontSize=9, leading=15, spaceAfter=8, textColor=colors.HexColor("#60676e")),
}
S=[]
def h(t): S.append(Paragraph(t,styles["heading"]))
def p(t): S.append(Paragraph(t,styles["text"]))
def small(t): S.append(Paragraph(t,styles["small"]))
S.append(Paragraph("城市滨海公共游憩空间供需适配研究",styles["title"]))
S.append(Paragraph("——用于 PaperTrail 阅读 Agent 的虚构示例论文",styles["title"]))
small("重要声明：本文全文由项目开发者编写，仅用于演示 PDF 解析、检索与证据定位；不代表真实研究、实际统计结果或正式发表的学术论文。")
h("摘要")
p("为展示研究任务驱动的文献阅读流程，本文以青岛市南区的滨海公共游憩空间为模拟研究对象，提出包含空间可达性、供给功能完整性和活动时空重叠度的评价框架。文章使用假设性数据和示例方法说明指标体系的构建、数据需求及结论边界。所有叙述均为演示用途。")
h("1 引言与研究问题")
p("旅游活动与居民日常活动可能在部分滨海公共空间形成时空叠加。公共游憩空间的供需适配研究不应仅统计绿地面积，还应考虑居民步行可达性、空间功能及高峰时段使用需求。本文提出三个演示性研究问题：（1）居民需求和访客活动在哪里发生空间重叠？（2）供给设施与活动需求在哪些片区可能不匹配？（3）哪些空间连接与存量更新策略有助于改进服务？")
h("2 研究范围")
p("本演示将青岛市南区作为行政研究单元，在模拟数据中进一步区分西部老城、中部滨海公共活动区和东部海滨片区。行政单元仅用于示例，具体研究边界及真实样本需要使用权威地理数据重新确认。")
S.append(PageBreak())
h("3 研究数据与研究方法")
p("3.1 数据来源。本示例假定具有城市绿地边界、道路步行网络、居住小区位置、公共服务设施位置和活动观察记录五类数据。绿地边界用于界定服务供给单元；道路网络用于步行距离计算；居住小区用于表示居民潜在需求；活动观察数据用于辅助识别高峰时段集聚情况。所有数据在本文中均为虚构或拟定数据，并未实际采集。")
p("3.2 研究方法。首先，根据服务对象和用地类型建立公共游憩空间清单。其次，利用 GIS 网络分析计算居民到各公共游憩空间入口的步行路径，并按500米和1000米两个距离阈值统计覆盖情况。然后，通过实地设施清单和访谈记录匹配活动需求与空间供给。最后，结合模拟活动观察表比较日常和假定旅游高峰时段的空间使用特征。")
h("4 评价指标体系（示例）")
p("指标一：步行可达覆盖率。定义为沿步行路网，在设定阈值内可以抵达至少一个公共游憩空间入口的居民点数量占全部居民点数量的比例。本例以500米和1000米作为两档阈值，所需数据为居民点、空间入口和可步行道路网络。该指标实际用于本演示的评价框架。")
p("指标二：功能供给匹配度。定义为研究单元已提供的主要活动设施种类与目标人群需求活动种类之间的匹配程度。所需数据为设施清单、活动需求类别和调查或访谈结果。该指标用于本演示的评价框架；具体权重与计算公式在本文中尚未确定。")
p("指标三：活动时空重叠度。通过对居民活动时段、游客活动时段及空间单元的交叉记录，识别两类活动频繁重叠的区域。所需数据为带时间标记的活动观察样本和空间位置。该指标仅作为描述性分析指标，不应直接解释为发生了使用冲突。")
p("文献综述中曾讨论空间句法和耦合协调模型，但本文没有实际使用这两类方法，不能将它们列为本研究的方法或评价指标。")
S.append(PageBreak())
h("5 演示性结果与讨论")
p("根据拟定的分析逻辑，步行网络连通性较弱的街区可能出现直线距离近、实际步行路径长的情形，因此道路网络分析比仅计算欧氏距离更适合表达步行服务可达性。此处表达的是方法选择的理由，并非真实实证研究得出的统计结论。")
p("活动时空重叠并不必然意味着居民回避或空间冲突。若要推断活动迁移，应进一步比较不同时间段的活动记录，或进行有针对性的居民访谈。演示数据不足以支持居民因游客增加而减少使用的因果结论。")
p("在空间优化层面，候选策略包括改善跨街步行连接、补充休憩设施、利用周边中小型绿地组织分散活动，以及在假定高峰期采用弹性管理方式。这些策略作为待检验建议，不表示其效果已得到验证。")
h("6 研究局限")
p("作者明确指出以下局限：第一，本文使用虚构或拟定数据，缺乏真实采样与实证检验；第二，功能供给匹配度尚未形成可重复计算的公式；第三，不同活动人群的时段行为需要进一步观察或访谈，不应从空间共存直接推断空间竞争；第四，结论仅用于展示阅读 Agent 的能力，无法推广至实际城市规划决策。")
h("7 结论")
p("本演示稿以研究任务为线索，列出了步行可达覆盖率、功能供给匹配度及活动时空重叠度三个示例指标，并为每项指标说明定义或逻辑、数据来源和适用边界。阅读 Agent 可以从中提取原文证据，但最终成果是否可用于真实研究，仍需人工核查和补充真实文献。")
small("备注：页面底部的页码用于验证 PDF 页序与印刷页码识别。所有章节和表述均为原创演示材料。")

def footer(c, d):
    c.saveState()
    c.setFont("STSong-Light",9)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(105*mm,16*mm,f"— {d.page} —")
    c.restoreState()

doc=SimpleDocTemplate(str(out),pagesize=(210*mm,297*mm),leftMargin=24*mm,rightMargin=24*mm,topMargin=22*mm,bottomMargin=25*mm,title="城市滨海公共游憩空间供需适配研究（演示稿）",author="PaperTrail 演示资料")
doc.build(S,onFirstPage=footer,onLaterPages=footer)
print(out)
