# 01 Cover — texts

> Edit text below. After save, run:
>   python3 assets/apply-texts.py <deck.html> <texts.md>
>
> Rules:
>   • Edit ONLY this file. Visual tweaks → overrides.css.
>     Layout / structure / new slides → re-ask Claude.
>   • Use `\n` to insert a line break (renders as <br>).
>   • Do NOT rename the slide-NN.field ids — they pair with HTML.

## slide-01 (cover) — 01 Cover
wordmark: 飞书
title: feishu-deck-h5\n设计语言展示
span: 设计语言团队
span_02: 2026.05.16

## slide-02 (agenda) — 02 Agenda
n: 01
title_zh: 字号体系与对齐规则
n_02: 02
title_zh_02: 十一种版式演示
n_03: 03
title_zh_03: 十个叙事 pattern
n_04: 04
title_zh_04: 富文本助手与卡片配方

## slide-03 (content-2col) — 03 Typography
demo_tag: 字号体系
title_zh: 4-tier 严格制 · 全 deck 只用 48 / 28 / 24 / 16
t_label: Title
t_px: 48 px
t_sample: 飞书企业 AI 客户案例集
t_label_02: Sub
t_px_02: 28 px
t_sample_02: 本季度增长 56% 的核心抓手
t_label_03: Body
t_px_03: 24 px
t_sample_03: 在 4 个一线门店做了 12 周实测,客单价提升 8.4%。
t_label_04: Foot
t_px_04: 16 px
t_sample_04: 数据来源 · 内部 BI 系统 · 截至 2026 Q1 周报

## slide-04 (content-2col) — 04 Alignment
demo_tag: 对齐默认
title_zh: 对齐三大默认 · framework 自动应用
bf_tag: BF10
bf_title: 混排大字小字默认 center,不要 baseline
bf_desc: 字号比 > 1.5× 的混排行(如 48 数字 + 24 中文)用 .mixed-row 工具类。
bf_tag_02: BF11
bf_title_02: big-stat hero 居中(opt-in modifier)
bf_desc_02: 2-col-hero 版式给 .hero 加 .is-centered,内容垂直水平居中,不再贴左边缘。
bf_tag_03: BF12
bf_title_03: 多卡 col 自动等高
bf_desc_03: col-text / col-visual 内有两张以上 canonical-card 时,通过 :has() 自动 flex column + flex:1。

## slide-05 (section) — 05 Section
demo_tag: Layout · section
chapter_num: 02.
title: 先进团队的工作方式
lede: 即时同步 · 共识对齐 · 闭环交付
pill_01: 飞书消息
pill_02: 飞书文档
pill_03: 多维表格
pill_04: 飞书会议

## slide-06 (content-3up) — 06 Content 3-up
demo_tag: Layout · content-3up
title_zh: 先进团队的三大工作方式
num: 01
ctitle_01: 即时同步
cbody_01: 30 万人组织 · 单条消息触达全员,平均三秒内已读。
num_02: 02
ctitle_02: 共识对齐
cbody_02: 所有讨论沉淀进 Wiki,决策可追溯,新成员第一天就能看到全貌。
num_03: 03
ctitle_03: 闭环交付
cbody_03: 从需求到上线 · 流程在多维表格中自动流转,每步都有责任人和时间戳。

## slide-07 (content-2col) — 07 Content 2-col
demo_tag: Layout · content-2col
title_zh: 让业务流程在表格里运转
lede: 多维表格把任务、工单、合同、人员、审批统一到一个可视化界面。
li: 看板 · 甘特 · 日历 · 卡片视图,一份数据多种视角
li_02: 关联字段把分散的表打成网,数据不再孤立
li_03: 触发器加自动化,把人工操作变成系统行为
li_04: 开放 API · 与 ERP / CRM / 自研系统双向同步
mock_placeholder: UI 截图 / 产品 mock 位置

## slide-08 (quote) — 08 Quote
demo_tag: Layout · quote
accent_text: 像一个团队
attrib: 某头部互联网公司 · CIO · 2026 Q1

## slide-09 (stats) — 09 Stats 4-up
demo_tag: Layout · stats
title_zh: 飞书带来的可量化结果
trend: ↑ 触达
unit: 秒
label: 30 万人组织全员消息送达时延
source: 数据来源 · 内部传输实测
trend_02: ↑ 已读
unit_02: %
label_02: 关键通知 30 分钟内已读率
source_02: 数据来源 · 12 家头部企业平均
trend_03: ↑ ROI
unit_03: ×
label_03: 部署 12 个月后协同 ROI 中位数
source_03: 数据来源 · 行业白皮书
trend_04: ↓ 决策
unit_04: 秒
label_04: 关键决策从发起到对齐时长
source_04: 数据来源 · 客户访谈

## slide-10 (big-stat) — 10 Big Stat
demo_tag: Layout · big-stat
unit: 万人
h3: 单一组织 · 统一协同
p: 飞书的消息、文档、视频会议在 30 万人量级下保持秒级响应,无需私有部署。

## slide-11 (image-text) — 11 Image-text
demo_tag: Layout · image-text
title: 现场决策\n从未离线
lede: 门店 · 产线 · 出差 · 远程 — 飞书让每一处节点都能即时被看到、被对齐。

## slide-12 (table) — 12 Table
demo_tag: Layout · table
title_zh: 飞书与传统办公套件对比
th_01: 能力
th_02: 飞书
th_03: 传统套件 A
th_04: 传统套件 B
td_01: 消息 · 文档 · 表格 · 会议
td_02: 原生集成
td_03: 多产品拼接
td_04: 多产品拼接
td_05: 多维表格自动化
td_06: 核心能力
td_07: 第三方插件
td_08: 不支持
td_09: 30 万人级消息触达
td_10: 3 秒内全员
td_11: 未公开
td_12: 未公开
td_13: 开放 API · Webhook
td_14: 全量开放
td_15: 受限
td_16: 受限

## slide-13 (timeline) — 13 Timeline
demo_tag: Layout · timeline
title_zh: 12 周落地路径
when: W1-2
what: 需求蓝图
desc: 访谈六个部门 · 输出协同地图与目标 KPI。
when_02: W3-5
what_02: 关键流程上线
desc_02: 销售 · HR · 财务三条核心流先跑通。
when_03: W6-8
what_03: 全员推广
desc_03: 分层培训 · 关键岗位 100% 接入。
when_04: W9-10
what_04: 数据搬迁
desc_04: 历史数据 / 工单系统切换完成。
when_05: W11-12
what_05: 复盘治理
desc_05: 复盘 KPI · 调整流程 · 形成长期治理机制。

## slide-14 (process) — 14 Process
demo_tag: Layout · process
title_zh: 需求到交付 · 四步成型
stnum: 01
h3: 提出
p: 任意一线员工在飞书消息发起,自动落入工单队列。
stnum_02: 02
h3_02: 对齐
p_02: 相关方在文档留痕讨论,关键决策沉淀到 Wiki。
stnum_03: 03
h3_03: 交付
p_03: 负责人在多维表格流转 · 每步责任人 + 时间戳可追溯。
stnum_04: 04
h3_04: 复盘
p_04: 会后自动生成纪要 · 关键指标进入下个周期。

## slide-15 (content-3up) — 15 Pattern N · 5-up Overview
demo_tag: Pattern N · 5-up Overview
title_zh: 本周南区周会 · 五个推进方向
ov_num: 01
ov_name: 商机管理
ov_desc: Q2/Q3 大扫除 · 周末截止
ov_num_02: 02
ov_name_02: AI 服务售卖
ov_desc_02: 售前帮扛 SOP 难题
ov_num_03: 03
ov_name_03: 新客建联
ov_desc_03: CXO 重点 · 56% 目标
ov_num_04: 04
ov_name_04: 市场活动
ov_desc_04: 五场密集落地
ov_num_05: 05
ov_name_05: 售前支持
ov_desc_05: HTML5 风格成主流

## slide-16 (content-3up) — 16 Pattern L · North-Star Map
demo_tag: Pattern L · North-Star Map
title_zh: 四个专项的北极星指标
idx: 01
h4: 门店管理
star_label: 北极星
star: 门店坪效
core_label: 核心售卖
core: 千店千面个性化
idx_02: 02
h4_02: 内容营销
star_label_02: 北极星
star_02: 投放 ROI
core_label_02: 核心售卖
core_02: 素材全生命周期
idx_03: 03
h4_03: 供应链
star_label_03: 北极星
star_03: 报损率
core_label_03: 核心售卖
core_03: 异常识别自动化
idx_04: 04
h4_04: 组织治理
star_label_04: 北极星
star_04: 决策时长
core_label_04: 核心售卖
core_04: 数字分身赋能

## slide-17 (content-3up) — 17 Pattern M · Scene Grid
demo_tag: Pattern M · Scene Grid
title_zh: 单一原则 · 跨行业适用
sc_name: 生鲜超市
sc_label: 个性化对象
sc_obj: 千店千策订货 · 调价
em: 报损率 ↓1pp = 头部一年增利 1-2 亿
sc_name_02: 便利店选品
sc_label_02: 个性化对象
sc_obj_02: 千店千策 SKU 组合
em_02: 单店日销 ↑5%+
sc_name_03: 连锁餐饮
sc_label_03: 个性化对象
sc_obj_03: 门店营销活动配比
em_03: 同店增长 ↑8 个百分点

## slide-18 (content-2col) — 18 Pattern D · Boundary Band
demo_tag: Pattern D · Boundary Band
title_zh: 不做 · 做 · 明确投入边界
column_pill: 不做
p: 为单点客户定制非通用功能
column_pill_02: 做
b: 5+ 客户共有的

## slide-19 (content-2col) — 19 Pattern J · Principle Band
demo_tag: Pattern J · Principle Band
title_zh: 三色原则带 · 战略选择的视觉钩子
principle: 专项优先
principle_02: 相邻扩展
principle_03: 战略例外
desc: 三色对应三种投入决策 · 每个原则配一色玻璃球前缀,让"为什么做这件事"在一行内说清。适用于战略层 / 资源分配 / 优先级讨论。

## slide-20 (content-2col) — 20 Pattern H+ · Two-hand Arch
demo_tag: Pattern H+ · Two-hand Arch
title_zh: 两手抓 · 一个决策人 · 一个底座
h3: 左手 · 协同效率
sub: 让每个一线节点都能被看到
n: 1
n_02: 2
n_03: 3
h3_02: 右手 · AI 落地
sub_02: 把隐形经验萃取到企业 AI
n_04: 4
n_05: 5
n_06: 6

## slide-21 (content-2col) — 21 Pattern I · 5-stage Pipeline
demo_tag: Pattern I · 5-stage Pipeline
title_zh: 端到端项目五阶段
num: 01
title_zh_02: 访谈
out_01: 六部门痛点输入
num_02: 02
title_zh_03: 蓝图
out_02: 协同地图 + 目标 KPI
num_03: 03
title_zh_04: 试点
out_03: 3 条核心流跑通
num_04: 04
title_zh_05: 推广
out_04: 全员接入 + 数据搬迁
num_05: 05
title_zh_06: 治理
out_05: 长期复盘机制

## slide-22 (content-3up) — 22 Pattern B · Verdict Matrix
demo_tag: Pattern B · Verdict Matrix
title_zh: 三种客户 · 三类介入决策
badge: 立即接入
ctitle_01: 先进型客户
cbody_01: 流程已成熟 · 把飞书带进去即可放大效果。学过来 → 教别人。
badge_02: 条件接入
ctitle_02: 中间型客户
cbody_02: 流程半成熟 · 需要先共创 1-2 个核心场景 · R&D VP 接洽。
badge_03: 暂缓
ctitle_03: 尚未就绪
cbody_03: 权限不到位 · 当下转化不可控 · 进入后续培育列表。

## slide-23 (content-2col) — 23 Pattern C · North-Star Chip
demo_tag: Pattern C · North-Star Chip
title_zh: 每个专项页都先钉北极星
north_star: 北极星指标 · 关键决策时长 < 60 秒
b: 一个能量化的目标

## slide-24 (content-2col) — 24 Pattern F · Evolution Chip
demo_tag: Pattern F · Evolution Chip
title_zh: 现阶段 → 未来 · 两行讲清演进
stage_tag: 现阶段
stage_body: 中心化协同 + 部门工作流
stage_tag_02: 未来
stage_body_02: 联邦化协同 + 跨域 AI 工作流
why: 两行紧凑布局把"我们今天在哪 / 我们要去哪"说清。比四行文字更适合一线汇报中"路线图速览"的场景。

## slide-25 (content-2col) — 25 Canonical Card Recipe
demo_tag: Helper · canonical-card
title_zh: .canonical-card · "标签 + 标题 + 描述" 卡片配方
cc_tag: 全员 · 来自侯
cc_title: 商机大扫除
cc_body: 清 Q2/Q3 不靠谱单 · 下次周会前完成。
cc_tag_02: 技能 · 杰森开源
cc_title_02: 本地部署 + API 接入
cc_body_02: 收到后同步到 A1 群,大家学起来 · 火山引擎模型组合调用待研究。
cc_tag_03: 行邵 → 庆豪
cc_title_03: 模型研究
cc_body_03: 研究如何使用火山引擎模型 + Claude Code 的组合调用。

## slide-26 (content-2col) — 26 Tag Taxonomy
demo_tag: Helper · 标签三分法
title_zh: 标签三档 · 选对 class · 不再"小标签太小"
lbl: .pill
pill_01: 辅助分页
note: 真 chrome · 16 Foot · 翻页指示 / 真元信息
lbl_02: .content-tag
content_tag: 技能 · 杰森开源
note_02: 承载内容的标签 · 24 Body 加粗品牌色 · 类别 / 状态 / 来源
lbl_03: .column-pill
column_pill: 困境
note_03: 栏目标题级别的胶囊 · 28 Sub · 不做/做 / 困境/解法 / 重点客群

## slide-27 (content-2col) — 27 CTA · Pullquote · Voice
demo_tag: Helper · CTA / Pullquote / Voice
title_zh: 三类强调助手 · 把页面"重锤"加上去
h3: 下一步 · 免费 90 分钟诊断工作坊
p: 架构师上门或线上 · 共同识别 1 个值得优先做的场景。
cta_btn: 启动诊断 →
pullquote: "不是让你再投一个大系统,而是先请几个不要工位的同事。"
q: 以前每天 8 点打开微信群看 200 条问题,现在群里是空的。精英销售终于能把时间放在打单。
who: 某饮料品牌 · 华东大区销售经理

## slide-28 (end) — 28 End
wordmark: 飞书
contact: 设计语言 · feishu-deck-h5
