"""pytest 配置文件。"""

import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)


def pytest_configure(config):
    """pytest 配置钩子。"""
    config.addinivalue_line("markers", "integration: 集成测试标记")
    config.addinivalue_line("markers", "slow: 慢速测试标记")


def pytest_collection_modifyitems(config, items):
    """修改测试收集。"""
    skip_integration = pytest.mark.skip(reason="需要 --integration 参数运行")

    for item in items:
        if "integration" in item.keywords and not config.getoption("--integration", default=False):
            item.add_marker(skip_integration)


def pytest_addoption(parser):
    """添加命令行选项。"""
    parser.addoption("--integration", action="store_true", default=False, help="运行集成测试")
