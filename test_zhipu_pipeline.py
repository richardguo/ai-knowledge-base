"""测试 ZHIPU API 的 pipeline 运行。"""

import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent
load_dotenv(project_root / ".env")

env = os.environ.copy()
env["LLM_API_BASE"] = env["ZHIPU_API_BASE_URL"]
env["LLM_API_KEY"] = env["ZHIPU_API_KEY"]
env["LLM_MODEL_ID"] = env["ZHIPU_MODEL_ID"]
env["PYTHONPATH"] = str(project_root)

print(f"使用 ZHIPU API: {env['LLM_API_BASE']}")
print(f"模型: {env['LLM_MODEL_ID']}")
print("=" * 60)

result = subprocess.run(
    [
        sys.executable,
        str(project_root / "pipeline" / "pipeline.py"),
        "--sources", "github",
        "--limit", "20",
        "--verbose",
    ],
    env=env,
    cwd=str(project_root),
)

sys.exit(result.returncode)
