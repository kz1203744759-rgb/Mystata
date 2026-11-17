# 前端组件结构与 ETL 流程

## 组件树

```text
App (frontend/main.jsx：数据、对话、模型设置、结果状态及 API 编排)
├─ Header（模型设置）
└─ ResizableWorkspace (ResizableWorkspace.jsx：拖拽和键盘调整三栏宽度)
   ├─ 数据工作区
   │  ├─ RawFilesPool（多文件拖拽、勾选与单文件挂载）
   │  ├─ ActiveDataset（当前 Stata frame 的数据状态）
   │  └─ VariableDictionary（主分析集变量）
   ├─ 研究对话
   │  ├─ Welcome（仅空对话显示）
   │  ├─ MarkdownMessage（AI 富文本，无原始 HTML 执行）
   │  └─ Composer（普通任务 / 自动切换 ETL）
   └─ 分析工作台
      ├─ 数据预览
      ├─ ETLWorkbench（模式、主键、字段映射、类型与确认）
      ├─ Do-file / OutputCard（探针折叠与错误修复入口）
      ├─ 结果矩阵
      └─ 产物下载
```

完整实现分别位于 `frontend/main.jsx`、`frontend/components/ResizableWorkspace.jsx`、`frontend/components/RawFilesPool.jsx`、`frontend/components/ETLWorkbench.jsx`、`frontend/components/MarkdownMessage.jsx`、`frontend/components/OutputCard.jsx` 和 `frontend/styles/workspace.css`。

## 实施步骤与接口

1. 三栏采用百分比分配；拖动分隔线或聚焦分隔线后按左右方向键调整，浏览器本地保存布局。
2. 文件池调用 `POST /api/raw-files` 批量上传，`GET /api/workspace` 恢复文件清单；上传不会替换当前主分析集。`POST /api/raw-files/{id}/activate` 将单表加载到 Stata 的新 frame。
3. ETL 标签页根据列名产生初步映射。`POST /api/etl/suggest` 可调用所选模型生成映射建议，默认只发送文件名、列名、标签与类型；勾选同意后可发送最多三条样例。用户必须核对。
4. `POST /api/etl/run` 校验字段名、来源和主键，生成并执行 Stata do-file。Stata 使用新 frame；失败时尝试切换回原 frame，只有成功并读取结果后才更新主分析集。脚本和结果保存在 `runs/`。
5. 执行输出仅在前端折叠已识别的 MCP 探针，原始日志仍保留；错误诊断按钮将代码及日志发送到当前模型。结果矩阵仍以实际 MCP 返回值为准。

## 数据语义与限制

- 原始文件池保存在 `datasets/raw/`；更换主分析集不会删除源文件。单次上传最多 20 个文件，单文件 60 MB；Excel 使用第一张表，CSV 必须是 UTF-8。
- 为保护前导零，ETL 时 CSV 字段以字符串导入；按需在映射表中明确选择“转数值”。转字符串使用 Stata 数值格式，无法找回数据源中本已丢失的前导零。
- Merge 默认使用 1:1 且仅保留匹配记录；也可显式选择 1:m、m:1 和其他保留方式。同名非主键的空值可被补全，非空冲突默认中止；用户也可在检查后选择主表或从表优先。Append 按勾选顺序追加。
- 目标字段名限定为最多 32 位的英文字母、数字和下划线，首位不能为数字；同一文件的源字段不能映射到多个目标。
- 新主分析集挂载后，模型上下文会重置；聊天内容可见但原有 Stata 模型估计结果不保证保留。服务重启后 Stata 内存与密钥需要重新配置。
- 数据整合页面的“AI 建议映射”只给出候选映射；通过对话明确请求合并时，预检通过后会自动执行并挂载，用户可在页面核对映射和日志。

## 测试

```powershell
npx vitest run frontend/tests/workspace.test.jsx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:RUN_REAL_STATA_TESTS='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_etl_real.py -v
```

## 标准化与合并前检查（本次更新）

- 默认识别证券代码为 `id` 并选择 `long` 标准化；数值必须为非负整数且不超过 Stata long 最大值 2147483620，显示格式为 `%06.0f`。并非所有名为 `id` 的字段都是证券代码，请人工选择相应规则。前导零仅为显示效果。
- 默认识别 `year` 等字段并转换为 `float` 年份，支持显式选择 YMD、MDY、DMY 字符串日期或 Stata 日日期；日期格式须用户确认。Excel 序列日期目前不自动识别。
- 除证券代码和确认的年份之外，字段默认不标准化；地区空格处理可手动选择。常见企业名称候选字段默认不保留，包括名为 `name` 的字段；应核对其实际含义，可重新勾选保留。
- Merge 默认剔除各源文件主键缺失行，合并后删除任一保留字段有缺失的行；预检展示剔除前后的行数。可调整该选项。Append 不默认剔除任何数据。
- `POST /api/etl/preview` 在独立 frame 和临时目录执行方案，读取真实 Stata 完整日志，并恢复之前的 frame；报告缺失主键、重复键、合并匹配及重叠字段冲突，并在日志中列出最多 5 条冲突样例。地区清理示例来自前 100 行。匹配关系错误时检查会在 Stata 报错处停止，后续统计不会产生。
- 非空冲突默认中止；用户也可以选择保留主表非空值或使用从表非空值。多表按勾选顺序依次处理，选用从表会覆盖之前同名的非空值。建议先看各字段冲突样例。用户可通过重新映射为不同字段保留两边值。
- AI 默认只发送元数据；仅在勾选同意后，每列最多发送前三行的样例（每值最多 100 字符）。模型不会自动验证指标的实际口径，需用户核对。
- 检查仅对当前方案有效，任何修改后需要在界面重新检查。检查执行并保存临时副本，不影响原始文件；正式整合成功后挂载新主分析集。
- Agent 的 `preview_merge` 负责预检，支持用户指定单个或多个键；明确请求合并且预检通过时由工作台自动执行并挂载。明确要求仅预检、预检失败或字段口径不确定时，不自动合并。不同年份口径和不确定的企业编码不能仅凭相似名称当作相同含义。
- 目前本地正在运行的服务不自动重启。新版页面暂存在 `web-build-next`，当旧服务退出、通过快捷方式启动新服务时，启动器才会切换页面，避免新旧接口不兼容。重启会结束 Stata 内存会话，API 密钥需重新填写。

## 工作区清理

通过项目快捷方式启动新的后台时，启动器会先清空项目内 `runs/`、`datasets/` 和 `.stata-tmp/` 中的文件及其子目录，再启动原有端口；重复打开仍在运行的服务不会自动清理。右上角“清空数据”按钮经确认后立即执行相同清理，卸载当前主分析集并清除执行记录，保留页面对话和当前模型密钥。任务运行中不能清理；文件外部原件、程序文件及依赖不在清理范围内。直接运行 uvicorn 不会执行快捷方式的启动清理流程。
