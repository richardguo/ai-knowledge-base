# AI Knowledge Base Assistant

## 1. Project Overview
An automated system that collects AI/LLM/Agent technical trends from GitHub Trending and Hacker News, analyzes content using AI, stores structured JSON data, and supports multi-channel distribution (Telegram/Feishu).

## 2. Tech Stack
- Python 3.12
- OpenCode + Domestic LLM
- LangGraph
- OpenClaw

## 3. Coding Standards
- PEP 8 compliance
- snake_case naming
- Google-style docstrings
- No bare print() statements (use logging)

## 4. Project Structure
```
.opencode/
├── agents/    # Agent definitions
├── skills/    # Specialized modules
knowledge/
├── raw/       # Raw collected data
├── articles/  # Processed knowledge entries
```

## 5. Knowledge Entry JSON Format
```json
{
    "id": "uuid4",
    "title": "Article Title",
    "source_url": "https://source.com/article",
    "summary": "AI-generated summary",
    "tags": ["LLM", "Agent"],
    "status": "new|processed|archived",
    "collected_at": "ISO 8601 timestamp"
}
```

## 6. Agent Roles
| Role       | Responsibilities          | Tools Used          |
|------------|---------------------------|---------------------|
| Collector  | Fetch trending content    | GitHub/HN APIs      |
| Analyzer   | Extract & structure data  | LLM summarization   |
| Curator    | Store & distribute        | DB/Notification APIs|

## 7. Red Lines
⚠️ **Absolute Prohibitions**
1. Hardcoding API credentials
2. Modifying production data without validation
3. Bypassing content copyright restrictions
4. Distributing unverified information