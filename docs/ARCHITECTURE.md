# 后端模块索引

这些模块当前仍位于项目根目录。下表说明其现有职责，不表示所有行为都已由真实 Stata 验证。

| 文件 | 主要职责 |
| --- | --- |
| `app.py` | Web 接口、工作区状态、模型与工具调用编排、Stata 会话及结果管理。 |
| `model_clients.py` | 不同模型服务接口的会话及工具调用适配。 |
| `mcp_launcher.py` | 为本地 mcp-stata 启动和 Windows 输出提供兼容处理。 |
| `profile_columns.py` | 读取数据文件的字段信息及相关检查。 |
| `merge_planner.py`、`merge_workflow.py` | 合并方案预览及多文件合并流程。 |
| `etl_engine.py` | 验证整合方案并生成数据清洗和合并的 Stata 代码。 |
| `winsor_engine.py` | 检查缩尾参数并生成对应 Stata 代码。 |
| `statistics_engine.py` | 生成并解析描述性统计和相关性分析结果。 |
| `did_engine.py` | 固定效应回归的验证、代码生成与结果解析。 |
| `event_study_engine.py` | 传统事件研究的模型生成和结果提取。 |
| `mediation_engine.py`、`mediation_workflow.py` | 中介分析的参数准备、代码生成和结果解析。 |
| `readable_do.py` | 为已有操作生成可读的 Stata 代码。 |
| `workspace_cleanup.py` | 清理本项目内的上传数据和运行产物；调用前应先保存需要的数据。 |

## 调整边界

`app.py` 使用自身位置确定项目根目录，并直接导入上述模块；启动脚本、测试和外部调用可能也依赖当前路径。移动或拆分后端前，应先建立可恢复的版本基线，核对导入、路径计算、补丁对象、启动流程、Stata 会话及生成文件路径，在隔离副本完成测试。不能只凭目录分类就断言移动后的运行行为完全相同。
