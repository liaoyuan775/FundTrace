# 合成材料生成

生成器会从空目录生成 CSV、PDF、DOCX、图片和 XLSX。XLSX 使用 `@oai/artifact-tool`。

```powershell
$node = "C:\Users\86136\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$artifact = "C:\Users\86136\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\@oai\artifact-tool\dist\artifact_tool.mjs"
python tools\generate_multisource_fixtures.py outputs\multisource_case_20260717 --node $node --artifact-tool-module $artifact
```

脚本会校验最终材料目录必须正好包含 10 份预期文件。
