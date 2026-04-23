@echo off
chcp 65001 >nul
echo MCP Knowledge Server
echo ====================
echo.
echo 知识库路径: %~dp0..\knowledge\articles
echo SSE 端点: http://localhost:8000/sse
echo.
echo 按 Ctrl+C 停止服务器
echo.

call D:\Development\PythonProject\Shared_Env\python312_opencode\Scripts\activate.bat
python %~dp0mcp_knowledge_server.py
