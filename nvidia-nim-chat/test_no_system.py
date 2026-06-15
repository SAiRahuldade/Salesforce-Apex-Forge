"""Test without system message."""

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")
endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Test 1: With system message
print("=" * 70)
print("Test 1: WITH system message")
print("=" * 70)

payload1 = {
    "model": "minimaxai/minimax-m3",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello"}
    ],
    "max_tokens": 50
}

response1 = requests.post(endpoint, headers=headers, json=payload1, timeout=120)
print(f"Status: {response1.status_code}")
data1 = response1.json()
print(f"Choices count: {len(data1.get('choices', []))}")
if data1.get('choices'):
    print(f"Response: {data1['choices'][0].get('message', {}).get('content', 'NO CONTENT')}")
else:
    print("Empty choices!")
print()

# Test 2: Without system message
print("=" * 70)
print("Test 2: WITHOUT system message")
print("=" * 70)

payload2 = {
    "model": "minimaxai/minimax-m3",
    "messages": [
        {"role": "user", "content": "Say hello"}
    ],
    "max_tokens": 50
}

response2 = requests.post(endpoint, headers=headers, json=payload2, timeout=120)
print(f"Status: {response2.status_code}")
data2 = response2.json()
print(f"Choices count: {len(data2.get('choices', []))}")
if data2.get('choices'):
    print(f"Response: {data2['choices'][0].get('message', {}).get('content', 'NO CONTENT')}")
else:
    print("Empty choices!")
print()

print("=" * 70)
print("Conclusion:")
if len(data1.get('choices', [])) == 0 and len(data2.get('choices', [])) > 0:
    print("✓ System messages cause empty responses!")
    print("  Solution: Remove system message from conversation")
elif len(data2.get('choices', [])) > 0:
    print("✓ Both work, but system message might have issues")
else:
    print("⚠️ Both failed - different issue")
print("=" * 70)
