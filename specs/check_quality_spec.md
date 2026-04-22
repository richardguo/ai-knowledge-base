# 背景描述
请帮我编写一个 Python 脚本 hooks/validate_json.py，用于校验由agent organizer产生的知识条目 JSON 文件。


# 需求
## 输入
- JSON文件的路径，缺省路径 .knowledge/articles/*.json
- index.json除外
- 支持单文件和多文件 （通配符 *.json）

需求：
1. 使用 dataclass 定义 DimensionScore 和 QualityReport 结构
2. 5 个评分维度及满分（加权总分 100 分）：
   - 摘要质量 (25 分)：>= 50 字满分，>= 20 字基本分，含技术关键词有奖励
   - 技术深度 (25 分)：基于文章 relevance_score 字段（1-10 映射到 0-25）
   - 格式规范 (20 分)：id、title、url、highlights、时间戳五项各 4 分
   - 标签精度 (15 分)：1-3 个合法标签最佳，有标准标签列表校验
   - 空洞词检测 (15 分)：不含"赋能""抓手""闭环""打通"等空洞词
3. 空洞词黑名单分中英两组：
   - 中文：赋能、抓手、闭环、打通、全链路、底层逻辑、颗粒度、对齐、拉通、沉淀、强大的、革命性的
   - 英文：groundbreaking、revolutionary、game-changing、cutting-edge 等
4. 等级标准：A >= 80, B >= 60, C < 60
5. 退出码：存在 C 级返回 1，否则返回 0

## 输出
- 输出可视化进度条 + 每维度得分 + 等级 A/B/C

## 参考文件
- agent organizer的输出参考文件： 例如 .opencode/agents/organizer.md

# 编码规范
- 遵循 PEP 8，使用 pathlib，不依赖第三方库
- 使用 pathlib 和 dataclass，不依赖第三方库
- 
# 运行环境
- 先激活 Python 环境，再执行脚本：

```
D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
chcp 65001
python hooks/validate_json.py [选项]
```

- 命令行用法：python hooks/validate_json.py <json_file> [json_file2 ...]
