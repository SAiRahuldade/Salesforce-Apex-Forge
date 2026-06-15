"""Debug script to see the actual API response."""

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")
api_base = os.getenv("NVIDIA_API_BASE", "https://integrate.api.nvidia.com/v1")
model = os.getenv("DEFAULT_MODEL", "minimaxai/minimax-m3")

endpoint = f"{api_base}/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": model,
    "messages": [
        {"role": "user", "content": "Hello! What is 2+2?"}
    ],
    "temperature": 0.7,
    "stream": False,
    "max_tokens": 100
}

print("=" * 70)
print("Debugging NVIDIA NIM API Response")
print("=" * 70)
print(f"Endpoint: {endpoint}")
print(f"Model: {model}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("=" * 70)
print("\nSending request...\n")

try:
    response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    
    print(f"Status Code: {response.status_code}")
    print("=" * 70)
    
    if response.status_code == 200:
        print("Raw Response:")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Error Response:")
        print(response.text)
        
except Exception as e:
    print(f"Error: {e}")
