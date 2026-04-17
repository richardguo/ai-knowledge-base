import requests
from typing import Dict, Any

def get_repo_info(owner: str, repo: str) -> Dict[str, Any]:
    """获取GitHub仓库的基本信息
    
    Args:
        owner: 仓库所有者
        repo: 仓库名称
    
    Returns:
        包含仓库信息的字典，结构为:
        {
            'stars': int, 
            'forks': int, 
            'description': str
        }
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Knowledge-Base"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        return {
            "stars": data["stargazers_count"],
            "forks": data["forks_count"],
            "description": data["description"]
        }
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"GitHub API请求失败: {str(e)}") from e
    except KeyError as e:
        raise RuntimeError(f"解析GitHub响应时出错: {str(e)}") from e