"""
MCP Knowledge Server 测试脚本

测试方式：
- stdio 模式：python test_mcp_client.py --transport stdio
- sse 模式：python test_mcp_client.py --transport sse
"""

import argparse
import asyncio
import json
import re
import subprocess
import sys

import httpx


async def test_stdio():
    """测试 stdio 模式"""
    print("=== 测试 stdio 模式 ===\n")
    
    init_params = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"}
    }
    
    init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init_params}
    initialized_msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    
    test_cases = [
        {
            "name": "测试 1：初始化",
            "messages": [init_msg],
            "expected_id": 1
        },
        {
            "name": "测试 2：列出工具",
            "messages": [init_msg, initialized_msg, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}],
            "expected_id": 2
        },
        {
            "name": "测试 3：搜索文章",
            "messages": [
                init_msg,
                initialized_msg,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_articles", "arguments": {"keyword": "agent", "limit": 3}}}
            ],
            "expected_id": 2
        },
        {
            "name": "测试 4：查看统计",
            "messages": [
                init_msg,
                initialized_msg,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "knowledge_stats", "arguments": {}}}
            ],
            "expected_id": 2
        }
    ]
    
    for test_case in test_cases:
        print(f"=== {test_case['name']} ===")
        
        proc = subprocess.Popen(
            [sys.executable, "utils/mcp_knowledge_server.py", "--transport", "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        
        for msg in test_case["messages"]:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
            if "id" in msg:
                response_line = proc.stdout.readline()
                if response_line:
                    try:
                        response = json.loads(response_line)
                        result = response.get("result", response.get("error", {}))
                        text = json.dumps(result, ensure_ascii=False, indent=2)
                        print(f"响应: {text[:500]}")
                    except json.JSONDecodeError:
                        print(f"响应 (原始): {response_line[:300]}")
        
        proc.terminate()
        print()
    
    print("=== 完整测试（一次性执行所有）===")
    proc = subprocess.Popen(
        [sys.executable, "utils/mcp_knowledge_server.py", "--transport", "stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )
    
    all_messages = [
        init_msg,
        initialized_msg,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "knowledge_stats", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_articles", "arguments": {"keyword": "agent", "limit": 3}}}
    ]
    
    expected_ids = [1, 2, 3, 4]
    response_idx = 0
    
    for msg in all_messages:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        if "id" in msg:
            response_line = proc.stdout.readline()
            if response_line:
                try:
                    response = json.loads(response_line)
                    result = response.get("result", response.get("error", {}))
                    text = json.dumps(result, ensure_ascii=False, indent=2)
                    print(f"响应 (id={expected_ids[response_idx]}): {text[:400]}")
                except json.JSONDecodeError:
                    print(f"响应 (原始): {response_line[:300]}")
                response_idx += 1
    
    proc.terminate()


async def test_sse():
    """测试 SSE 模式"""
    print("=== 测试 SSE 模式 ===\n")
    print("请确保服务器已启动: python utils/mcp_knowledge_server.py\n")
    
    base_url = "http://localhost:8000"
    messages_url = None
    responses = []
    
    async def sse_listener():
        """监听 SSE 事件"""
        nonlocal messages_url
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", f"{base_url}/sse") as response:
                print(f"SSE 连接状态: {response.status_code}")
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.startswith("/") and "session_id" in data:
                            messages_url = f"{base_url}{data}"
                            print(f"获取到消息端点: {messages_url}\n")
                        else:
                            try:
                                msg = json.loads(data)
                                responses.append(msg)
                            except json.JSONDecodeError:
                                pass
    
    async def send_and_wait(requests: list, wait_time: float = 1.0):
        """发送请求并等待响应"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            for req in requests:
                r = await client.post(messages_url, json=req)
                if r.status_code != 202:
                    print(f"POST 错误: {r.status_code}")
        await asyncio.sleep(wait_time)
    
    listener_task = asyncio.create_task(sse_listener())
    
    # 等待 SSE 连接建立并获取消息端点
    # Python for-else 语法：如果循环被 break 打断，则跳过 else 块
    for _ in range(50):
        if messages_url:
            break  # 获取到端点，跳出循环
        await asyncio.sleep(0.1)
    else:
        # 循环正常结束（未获取到端点），执行 return 退出函数
        print("错误: 未能在5秒内获取到消息端点")
        listener_task.cancel()
        return
    
    # 只有 break 跳出循环后（成功获取端点），才会执行以下代码
    init_params = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"}
    }
    
    init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init_params}
    initialized_msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    
    test_cases = [
        {
            "name": "测试 1：初始化",
            "messages": [init_msg],
            "expected_ids": [1]
        },
        {
            "name": "测试 2：列出工具",
            "messages": [init_msg, initialized_msg, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}],
            "expected_ids": [1, 2]
        },
        {
            "name": "测试 3：搜索文章",
            "messages": [
                init_msg,
                initialized_msg,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "search_articles", "arguments": {"keyword": "agent", "limit": 3}}}
            ],
            "expected_ids": [1, 2]
        },
        {
            "name": "测试 4：查看统计",
            "messages": [
                init_msg,
                initialized_msg,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "knowledge_stats", "arguments": {}}}
            ],
            "expected_ids": [1, 2]
        }
    ]
    
    for test_case in test_cases:
        responses.clear()
        print(f"=== {test_case['name']} ===")
        await send_and_wait(test_case["messages"])
        
        for resp in responses:
            if resp.get("id") in test_case["expected_ids"]:
                result = resp.get("result", resp.get("error", {}))
                text = json.dumps(result, ensure_ascii=False, indent=2)
                print(f"响应: {text[:400]}")
        print()
    
    print("=== 完整测试（一次性执行所有）===")
    responses.clear()
    
    all_messages = [
        init_msg,
        initialized_msg,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "knowledge_stats", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_articles", "arguments": {"keyword": "agent", "limit": 3}}}
    ]
    
    await send_and_wait(all_messages, wait_time=1.5)
    
    for resp in sorted(responses, key=lambda x: x.get("id", 0)):
        result = resp.get("result", resp.get("error", {}))
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(f"响应 (id={resp.get('id')}): {text[:350]}")
    
    listener_task.cancel()


def main():
    parser = argparse.ArgumentParser(description="MCP Knowledge Server 测试")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="测试模式: stdio 或 sse"
    )
    args = parser.parse_args()
    
    if args.transport == "stdio":
        asyncio.run(test_stdio())
    else:
        asyncio.run(test_sse())


if __name__ == "__main__":
    main()
