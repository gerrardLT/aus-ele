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
4. 需要长期保留的知识沉淀入 `docs/`（任务记录/调研文档），数据样本入 `data/`（需评审）；
5. `.gitignore` 已覆盖：`workspace/`、`logs/`、`*.log`、`tmp_*`、`*-live.*.log`、`artifacts-*.png`、`output/`、`__pycache__/`；新增产物类型时同步补充规则。