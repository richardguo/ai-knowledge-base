# 背景描述
请帮我编写一个 Python 脚本 hooks/validate_json.py，用于校验由agent organizer产生的知识条目 JSON 文件。


# 需求
## 输入
- JSON文件的路径，缺省路径 .knowledge/articles/*.json
- index.json除外
- 支持单文件和多文件

## 校验项
1. JSON 是否能正确解析
2. 必填字段使用 dict[str, type] 格式，同时校验字段存在性和类型：
   id(str), title(str), url(str), summary(str), tags(list)
3. 检查 URL 格式（https?://...）
4. 检查summary最少 20 字、标签至少 1 个
5. 检查 relevance_score（如有）是否在 1-10 范围，audience（如有）是否为 beginner/intermediate/advanced

## 输出
- 打印到控制台
- 校验通过 exit 0，失败 exit 1 + 错误列表 + 汇总统计

## 参考文件
- agent organizer的输出参考文件： 例如 .opencode/agents/organizer.md

# 编码规范
- 遵循 PEP 8，使用 pathlib，不依赖第三方库

# 运行环境
- 先激活 Python 环境，再执行脚本：

```
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001
python hooks/validate_json.py [选项]
```

- 命令行用法：python hooks/validate_json.py <json_file> [json_file2 ...]
