一定要用简体中文和我沟通
无用的命令行终端 要及时清理
任务完成后 一定要更新task 文档 
临时文件也要及时清理
如果遇到无法一次性写入文档 请分段写入

## 文件分类规范（运行期产物一律不入库）

根目录保持干净，只放配置/入口/核心文档。运行期产物统一放 `workspace/`（已整体 gitignore）：

| 分类 | 目录 | 存放内容 | 示例 |
|---|---|---|---|
| 运行日志 | `workspace/logs/` | 后台进程输出、回填/回测/冒烟日志 | `backend-live.out.log`、`rolling_backtest_*.log` |
| 临时文件 | `workspace/tmp/` | 一次性脚本/探针/中间产物，用后即删 | `tmp_*.py`、`tmp_*.ps1` |
| 图片/截图 | `workspace/artifacts/` | 演示截图、图表导出 | `artifacts-*.png` |
| 生成报告 | `workspace/reports/` | 脚本生成的临时报告（正式报告入 docs/） | 回测汇总 txt |

硬性规则：
1. 新建任何日志/临时/产物文件必须先落到上表对应目录，禁止写根目录；
2. 临时文件（`tmp_*`）任务结束当天删除；确需保留的移入 `workspace/` 对应分类；
3. `output/` 为 agent/脚本运行输出（已 gitignore），A/B 数据等调研产物放这里；
4. 需要长期保留的知识沉淀入 `docs/`（按下表子分类），数据样本入 `data/`（需评审）；
5. `.gitignore` 已覆盖：`workspace/`、`logs/`、`*.log`、`tmp_*`、`*-live.*.log`、`artifacts-*.png`、`output/`、`__pycache__/`；新增产物类型时同步补充规则；
6. **假设登记纪律（2026-08-12）**：影响分析结论的关键参数（压缩因子/参考电池/模型分布参数/合约锚点等）一律登记在 `data/assumptions_registry.json`；参数变更必须同步更新登记表并记录 `modified_by` / `last_calibrated`；新增关键假设时补登记条目（status 可选 wired/audit_only/pointer）。

## docs/ 子分类规范（2026-08-11 归类后）

docs/ 顶层不再放散落 md，一律按类别入子目录：

| 子目录 | 存放内容 | 命名约定 |
|---|---|---|
| `docs/tasks/` | 任务记录（每轮实施/修复/验收的经过与结论） | `任务记录-YYYY-MM-DD-主题.md` |
| `docs/research/` | 调研文档（范式/技术/交叉验证/调研计划） | `调研-主题.md`、`调研计划-日期-主题.md` |
| `docs/strategy/` | 业务策略方案（定位/首页/政策/竞品） | `主题方案/建议/总纲.md` |
| `docs/architecture/` | 架构/总册/契约说明 | `主题.md` |
| `docs/deployment/` | 部署与 CI/CD 说明 | `主题.md` |
| `docs/design/` | UI 设计规范（Stitch DESIGN.md、tokens、prompts） | — |
| `docs/diagrams/` | 架构图集 | `NN-主题图.md` |
| `docs/_archive/`、`docs/_references/` | 历史归档 / 外部参考资料（只读引用） | — |

硬性规则：
1. 新建文档直接入对应子目录，禁止放 docs/ 顶层；
2. 代码/测试按路径引用 docs 时（如 `web/src/lib/australiaDocsConsistency.test.js`），移动文档必须同步更新引用路径并跑通相关测试；
3. 任务完成更新任务记录时写入 `docs/tasks/` 对应文件。