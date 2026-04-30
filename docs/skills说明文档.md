> 状态：会话型参考文档，可能快速过时
>
> 说明：
> - skills 的可用列表取决于当前运行环境、会话上下文和本机安装情况。
> - 本文更适合作为“如何理解和选择 skill”的辅助说明，不应视为永远准确的全量清单。
> - 如果本文与当前实际可用 skills 不一致，应以会话内实时暴露的 skills 列表为准。
> - 因此，本文中的 skill 数量统计和部分示例名称都可能失效。

# Skills 说明文档

更新时间：2026-04-14

本文件基于当前会话可用的 skills 白名单整理，用于快速查看每个 skill 的用途、适用场景和推荐组合。

当前可直接使用的 skills 共 `89` 个。

说明：

- 本文档按“当前会话可用”整理，不等同于本机磁盘上所有目录。
- 本机本地目录里能看到 `gstack`，但它不在当前会话的显式可用白名单中，所以本文不纳入。
- skill 不会自动跨轮继承；如果下一轮还要继续用，最好继续明确提到对应名称。

## 使用规则

1. 当用户显式提到某个 skill 名称时，应优先使用该 skill。
2. 当任务和某个 skill 的描述明显匹配时，也应主动使用该 skill。
3. 多个 skill 可以组合，但应优先选择最小必要集合，避免无意义堆叠。
4. 设计类 skill 适合处理界面、布局、视觉、可用性问题。
5. 产品类 skill 适合做分析、调研、战略、PRD、用户研究和商业判断。
6. 工程类 skill 适合做计划、调试、测试、代码审查和交付收尾。

## 常用推荐组合

| 场景 | 推荐 skills |
| --- | --- |
| 新功能从 0 到 1 | `brainstorming` + `writing-plans` + `executing-plans` |
| Bug 修复 | `systematic-debugging` + `test-driven-development` + `verification-before-completion` |
| 提交前代码审查 | `requesting-code-review` + `verification-before-completion` |
| 处理别人给的 review 意见 | `receiving-code-review` |
| 前端界面重做 | `frontend-design` + `arrange` + `typeset` + `polish` |
| 提升体验和动效 | `animate` + `delight` + `polish` |
| 做产品发现 | `problem-statement` + `jobs-to-be-done` + `discovery-process` |
| 写 PRD | `prd-development` + `user-story` + `roadmap-planning` |
| 做商业分析 | `business-health-diagnostic` + `finance-metrics-quickref` + `prioritization-advisor` |
| 查找或安装新技能 | `find-skills` + `skill-installer` |

## 一、设计与前端体验类

| Skill | 作用 | 适用场景 |
| --- | --- | --- |
| `adapt` | 让设计适配不同屏幕、设备和上下文。 | 响应式设计、移动端适配、断点和跨设备兼容。 |
| `animate` | 为界面增加有意义的动画和微交互。 | 需要转场、动效、hover 反馈、页面更有生命力。 |
| `arrange` | 优化布局、间距和视觉节奏。 | 页面拥挤、层级弱、对齐和留白不舒服。 |
| `audit` | 对可访问性、性能、主题、响应式和反模式做技术审计。 | 需要做质量检查、可访问性检查、性能审计。 |
| `bolder` | 让过于保守的设计更有冲击力和个性。 | 页面太平、太安全、缺少视觉特色。 |
| `clarify` | 优化 UX 文案、标签、说明和错误提示。 | 文案不清楚、指引难懂、提示不友好。 |
| `colorize` | 用更有策略的颜色让界面更鲜活。 | 页面太灰、太单调、缺少温度和辨识度。 |
| `critique` | 从 UX 视角做系统化评估和反馈。 | 需要设计评审、体验打分、问题归纳。 |
| `delight` | 给界面增加惊喜感、个性和记忆点。 | 想做更有趣、更讨喜、更有品牌感的体验。 |
| `distill` | 把复杂设计收敛到更简洁清晰的形态。 | 想去噪、减法、聚焦核心信息。 |
| `extract` | 提取可复用组件、设计 token 和模式。 | 搭建设计系统、整理重复 UI。 |
| `frontend-design` | 生成高质量、非模板化的前端界面设计方案。 | 做页面、组件、应用壳层和高完成度视觉实现。 |
| `frontend-skill` | 面向网页和应用的强视觉落地能力，强调克制而高级的界面。 | 需要做 landing page、网页、Demo UI。 |
| `harden` | 提升界面的鲁棒性和边界情况处理能力。 | 错误态、i18n、溢出、空状态、极端输入。 |
| `normalize` | 把 UI 重新拉回设计系统标准。 | 样式漂移、token 不统一、控件风格不一致。 |
| `onboard` | 设计或优化新用户引导和首屏体验。 | onboarding、空状态、首次使用、激活流程。 |
| `optimize` | 诊断和优化前端性能。 | 页面卡顿、加载慢、动效不流畅、包体过大。 |
| `overdrive` | 追求极致展示效果和技术表现力。 | 想做 wow 效果、复杂动效、技术型视觉体验。 |
| `polish` | 做最终的视觉和交互收尾。 | 上线前抛光、细节修正、统一质感。 |
| `quieter` | 把过于吵闹或刺激的视觉降噪。 | 页面太炸、太花、侵略性过强。 |
| `teach-impeccable` | 一次性沉淀项目设计上下文到 AI 配置。 | 刚接手新项目，想建立长期设计准则。 |
| `typeset` | 强化字体、层级、字重和可读性。 | 排版松散、字体选择差、信息层级不清。 |

## 二、产品、商业与研究类

| Skill | 作用 | 适用场景 |
| --- | --- | --- |
| `acquisition-channel-advisor` | 用单位经济、质量和可扩展性评估获客渠道。 | 决定某个渠道该扩量、测试还是停止。 |
| `ai-shaped-readiness-advisor` | 评估产品是否已经具备 AI-first 或 AI-shaped 能力。 | 判断 AI 成熟度和下一步能力建设重点。 |
| `altitude-horizon-framework` | 用“高度”和“时间地平线”分析管理者能力跃迁。 | PM 向 Director 转型、判断 scope 和 horizon。 |
| `business-health-diagnostic` | 从增长、留存、效率、资本使用诊断业务健康度。 | 做经营复盘、发现最紧急的商业问题。 |
| `company-research` | 产出公司研究简报。 | 面试准备、竞品研究、合作调研、行业切入。 |
| `context-engineering-advisor` | 判断是“堆上下文”还是“做上下文工程”。 | AI 工作流臃肿、脆弱、不好驾驭时。 |
| `customer-journey-map` | 制作客户旅程图。 | 诊断完整用户旅程、识别断点和机会点。 |
| `customer-journey-mapping-workshop` | 用工作坊方式共创客户旅程图。 | 需要多方协作梳理阶段、情绪、痛点、指标。 |
| `director-readiness-advisor` | 指导 PM 向 Director 的准备、面试和落地。 | 管理岗位提升、角色切换。 |
| `discovery-interview-prep` | 帮你设计用户访谈。 | 做问题验证、流失访谈、需求探索。 |
| `discovery-process` | 跑完整 discovery 流程。 | 从假设、访谈、综合到验证的全链路发现。 |
| `eol-message` | 写清晰、体面的产品或功能下线公告。 | 产品退役、方案取消、功能下线。 |
| `epic-breakdown-advisor` | 把 Epic 拆成可交付故事。 | backlog 太大、很难估算或排序。 |
| `epic-hypothesis` | 把大型项目写成可验证的假设。 | 路线图前置定义、战略项目立项。 |
| `executive-onboarding-playbook` | 设计 VP/CPO 等高层的 30/60/90 天入职诊断路径。 | 新高管 onboarding、避免过早拍板。 |
| `feature-investment-advisor` | 用 ROI、收入影响和成本结构评估功能投入。 | 判断某功能值不值得投资源。 |
| `finance-based-pricing-advisor` | 用 ARPU、转化、流失、NRR 评估定价动作。 | 涨价、降价、改套餐前分析。 |
| `finance-metrics-quickref` | 快速查 SaaS 财务指标定义和公式。 | 开会、分析、写文档时快速确认概念。 |
| `jobs-to-be-done` | 结构化梳理用户任务、痛点和收益。 | 做需求洞察、定位、问题定义。 |
| `lean-ux-canvas` | 用 Lean UX Canvas 梳理业务问题和假设。 | 需求探索、团队对齐、找下一步学习目标。 |
| `opportunity-solution-tree` | 构建 OST 树。 | 从目标到机会再到方案的系统拆解。 |
| `pestel-analysis` | 分析政治、经济、社会、技术、环境、法律因素。 | 外部环境变化影响路线图或产品时。 |
| `pol-probe` | 设计最低成本的“生命迹象验证”。 | 高风险假设先做低成本验证。 |
| `pol-probe-advisor` | 帮你挑选最合适的 PoL 验证方式。 | 不知道该用问卷、落地页、人工服务还是 Demo。 |
| `positioning-statement` | 产出 Geoffrey Moore 风格定位语句。 | 明确目标用户、价值和差异化。 |
| `positioning-workshop` | 通过工作坊方式梳理定位。 | 产品定位模糊、信息表达混乱。 |
| `prd-development` | 形成结构化 PRD。 | 把发现阶段输出转成可执行需求文档。 |
| `press-release` | 用 Amazon 风格 PR/FAQ 先定义价值。 | 新产品或重大功能立项前。 |
| `prioritization-advisor` | 选择合适的优先级框架。 | RICE、ICE、Value/Effort 之间难选择。 |
| `problem-framing-canvas` | 用问题框架画布重新定义问题。 | 团队太快跳方案，需要先定义真问题。 |
| `problem-statement` | 写清晰的用户问题陈述。 | 需求模糊、要先对齐用户和痛点。 |
| `product-sense-interview-answer` | 帮你组织产品 sense 面试回答。 | PM 面试中的 improve/build/design 类题目。 |
| `product-strategy-session` | 从定位、发现到路线图跑完整策略会话。 | 做产品战略、年度方向、重大转向。 |
| `proto-persona` | 基于现有信息快速形成 proto persona。 | 研究不充分但要先形成工作假设。 |
| `recommendation-canvas` | 评估一个 AI 产品想法值不值得做。 | AI 方向判断、建议方案筛选。 |
| `roadmap-planning` | 做战略路线图规划。 | 版本节奏、优先级和资源排布。 |
| `saas-economics-efficiency-metrics` | 分析 SaaS 单位经济和资本效率。 | 看业务是否能健康扩张。 |
| `saas-revenue-growth-metrics` | 计算和分析收入、留存、增长指标。 | 看产品增长动能和流失结构。 |
| `storyboard` | 做 6 格故事板。 | 展示用户从问题到解决方案的叙事。 |
| `tam-sam-som-calculator` | 估算 TAM / SAM / SOM。 | 市场规模分析、商业计划、路演。 |
| `user-story` | 产出用户故事和 Gherkin 验收标准。 | 把需求写成研发能直接执行的格式。 |
| `user-story-mapping` | 产出用户故事地图。 | 规划 workflow、MVP 切片、backlog。 |
| `user-story-mapping-workshop` | 用工作坊方式共创用户故事地图。 | 团队一起梳理用户流程和版本切片。 |
| `user-story-splitting` | 把大故事拆成小故事。 | 单个故事太大、依赖太多、不好排期。 |
| `vp-cpo-readiness-advisor` | 指导向 VP/CPO 角色跃迁。 | 高层产品领导岗位转型。 |
| `workshop-facilitation` | 帮你稳定地主持互动式工作坊。 | 需要控制节奏、追踪进度和输出结构。 |

## 三、工程、调试与开发工作流类

| Skill | 作用 | 适用场景 |
| --- | --- | --- |
| `brainstorming` | 在真正动手前先澄清目标、约束、方案空间。 | 创建功能、改行为、做复杂改动之前。 |
| `dispatching-parallel-agents` | 识别并拆分可并行处理的独立任务。 | 多个子任务之间没有共享状态、可并行推进。 |
| `executing-plans` | 根据既有实施计划推进任务。 | 已经有清晰方案，需要开始执行。 |
| `find-skills` | 帮你查找或推荐合适的 skill。 | 不确定某项能力有没有现成 skill。 |
| `finishing-a-development-branch` | 指导如何收尾、合并或发 PR。 | 开发完成、测试通过、准备集成时。 |
| `receiving-code-review` | 理性处理外部 code review 意见。 | 收到 reviewer 意见，需要判断是否采纳。 |
| `requesting-code-review` | 在完成阶段发起代码审查。 | 做完功能、修复后，想做正式 review。 |
| `skill-authoring-workflow` | 把原始内容整理成合规 skill。 | 写或维护 skill 本身。 |
| `subagent-driven-development` | 用子 agent 执行当前会话中的独立任务。 | 用户明确允许委派，且适合拆分实施。 |
| `systematic-debugging` | 先系统定位问题，再给修复方案。 | 任何 bug、异常、测试失败、行为不符。 |
| `test-driven-development` | 用 TDD 驱动功能或修复实现。 | 需要先写测试再写代码时。 |
| `using-git-worktrees` | 用 git worktree 隔离工作环境。 | 当前工作区太脏，或需要开独立分支空间。 |
| `using-superpowers` | 帮你理解和使用这套 skill / superpower 体系。 | 想知道技能怎么触发、怎么组合时。 |
| `verification-before-completion` | 在宣称完成前先执行验证。 | 提交前、交付前、回复“已完成”前。 |
| `writing-plans` | 根据需求写实施计划。 | 多步骤任务、复杂改造、重要重构。 |
| `writing-skills` | 创建或更新 skill 文件与说明。 | 你要自己写新 skill 或维护现有 skill。 |

## 四、系统与平台能力类

| Skill | 作用 | 适用场景 |
| --- | --- | --- |
| `imagegen` | 生成或编辑位图图像。 | 需要海报、插画、贴图、位图资产。 |
| `openai-docs` | 使用官方 OpenAI 文档回答 API / 模型问题。 | 了解 OpenAI 产品、API、模型升级和文档。 |
| `plugin-creator` | 创建或脚手架化本地 plugin。 | 需要新建 Codex 插件目录和元数据。 |
| `skill-creator` | 指导如何创建一个高质量 skill。 | 从零设计新的 skill。 |
| `skill-installer` | 安装已有 skill。 | 需要把外部 skill 装到本机环境。 |

## 如何快速选 skill

如果你只是想快速判断用哪个，可以按下面的思路：

- 做界面：优先看“设计与前端体验类”
- 做产品分析：优先看“产品、商业与研究类”
- 修 bug / 写代码：优先看“工程、调试与开发工作流类”
- 查 OpenAI 文档、装 plugin、装 skill：优先看“系统与平台能力类”

## 后续建议

如果你后面希望我继续维护这份文档，可以再加 3 个扩展版本：

1. `skills速查版.md`
   只保留名字、用途、适用场景，适合平时查阅。
2. `skills推荐路线图.md`
   按“产品经理 / 工程师 / 设计师 / 创业者”分别推荐最常用 skill 组合。
3. `skills使用示例.md`
   给每个 skill 配一条典型触发语句和一个真实使用例子。
