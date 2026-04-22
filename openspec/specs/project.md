
## 技术栈
Python 3.12 · 无框架 · 本地开发 · git 托管

## 运行环境
- 先激活 Python 环境，再执行脚本：

```
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001
```

## 关键数据契约
- knowledge/raw/github-search-*.json · collector 产出 · schema: openspec/specs/schemas/collector-output.json
- knowledge/raw/github-trending-*.json · collector 产出 · schema: openspec/specs/schemas/collector-output.json
- knowledge/processed/analyzer-*.json · analyzer 产出 · schema: openspec/specs/schemas/analyzer-output.json
- knowledge/articles/????-??-??-*.json · organizer 产出 · schema: openspec/specs/schemas/knowledge-article.json
- knowledge/articles/index.json · organizer 产出 · schema: openspec/specs/schemas/index.json

## 项目约定
- git hook 放 .git/hooks/ · 不用 husky
- pre-commit 失败必须 block · 不用 warn-only
