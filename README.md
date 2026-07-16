# FundTrace 电诈资金链穿透研判系统

FundTrace 是面向公安刑侦电诈资金研判的内网单机应用。它把案件材料接收、流水提取、人工校核、确认版 CSV、涉诈起点和资金拓扑放在一条可追溯流程中。

## 快速启动

环境要求：Python 3.11、Node.js 20。

```powershell
cd D:\AgentLearning\FundTrace
pip install -r requirements.txt
.\start.ps1
```

浏览器访问 `http://127.0.0.1:8000`。首次进入会自动建立一个包含 52 个账户、118 笔流水的虚构演示案件。

开发模式：运行 `.\dev.ps1`，访问 `http://127.0.0.1:5173`。

## 数据目录

每个案件位于 `data/cases/{case_id}`，包含：

- `materials`：原始材料与 SHA-256 清单；
- `extracted`：PDF、Word、表格和图片的提取片段；
- `drafts`：待人工校核的流水 JSONL；
- `versions`：不可覆盖的确认版 CSV 与校验信息；
- `analysis`：起点和分析结果；
- `exports`：导出结果；
- `audit`：追加式操作审计。

Repository 接口将业务逻辑与文件持久化隔离，后续可增加 SQLite 或 PostgreSQL 实现。

## 材料与模型

- 内置读取 CSV、XLSX、DOCX、文本 PDF、常见图片和 ZIP。
- 图片会进入视觉能力适配器；RAR 需在 `RAR_EXECUTABLE` 配置受控解包程序。
- Qwen 使用 OpenAI 兼容内网接口，变量见 `.env.example`。
- 模型输出永远是待校核草稿，只有人工确认记录才能生成正式 CSV 和涉诈起点。

不要提交 `.env`。当前对话中暴露过的 API 密钥在正式试用前应轮换。

## 资金归因

系统同时提供时间优先 FIFO、保守下限、可能上限和比例分摊。所有结果均标记为研判推定，单一受害人的累计归因不得超过其确认起点金额。

## 测试

```powershell
python -m pytest
npm test --prefix frontend
npm run build --prefix frontend
$env:PYTHONPATH='backend'; python benchmark.py
```

后端测试覆盖人工确认门、安全解包、复杂演示图和 5 万元混同资金回归案例。前端测试固定案件、材料、校核、起点、研判和原始流水工作区。

