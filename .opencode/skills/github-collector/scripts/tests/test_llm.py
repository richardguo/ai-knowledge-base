"""测试 LLM API"""
import requests
import os
from dotenv import load_dotenv

load_dotenv('/.env')

api_base = os.getenv('LLM_API_BASE', '')
api_key = os.getenv('LLM_API_KEY', '')
model_id = os.getenv('LLM_MODEL_ID', '')

print(f'Base: {api_base}')
print(f'Key: {api_key[:20]}...')
print(f'Model: {model_id}')

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
}

payload = {
    'model': model_id,
    'messages': [{'role': 'user', 'content': '你好，请用一句话介绍你自己'}],
    'max_tokens': 100,
}

url = api_base.rstrip('/') + '/chat/completions'
print(f'URL: {url}')

response = requests.post(url, headers=headers, json=payload, timeout=30)
print(f'Status: {response.status_code}')
print(f'Response: {response.text[:1000]}')
