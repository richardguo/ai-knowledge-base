import requests

def get_repo_info(owner, repo):
    """
    Fetches basic information about a GitHub repository.
    
    Args:
        owner (str): Repository owner username
        repo (str): Repository name
        
    Returns:
        dict: Dictionary containing stars, forks, and description
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(url)
    
    if response.status_code != 200:
        return None
        
    data = response.json()
    return {
        'stars': data['stargazers_count'],
        'forks': data['forks_count'],
        'description': data['description']
    }

if __name__ == "__main__":
    # Example usage
    info = get_repo_info("torvalds", "linux")
    if info:
        print(f"Stars: {info['stars']}")
        print(f"Forks: {info['forks']}")
        print(f"Description: {info['description']}")