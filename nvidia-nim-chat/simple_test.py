"""Simple test with better error handling and longer timeout."""

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("NVIDIA_API_KEY")
print(f"API Key loaded: {api_key[:20]}..." if api_key else "No API key found")

endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Simpler payload
payload = {
    "model": "minimaxai/minimax-m3",
    "messages": [
        {"role": "user", "content": "Say hello"}
    ],
    "max_tokens": 50
}

print("\n" + "=" * 70)
print("Testing NVIDIA NIM API Connection")
print("=" * 70)
print(f"\nEndpoint: {endpoint}")
print(f"Model: {payload['model']}")
print("\nSending request with 60s timeout...\n")

try:
    response = requests.post(
        endpoint, 
        headers=headers, 
        json=payload, 
        timeout=60,
        verify=True
    )
    
    print(f"✓ Response received!")
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        data = response.json()
        print("=" * 70)
        print("SUCCESS! Full Response:")
        print("=" * 70)
        print(json.dumps(data, indent=2))
        print("\n" + "=" * 70)
        
        # Try to extract the message
        if "choices" in data and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content", "")
            print(f"\n✓ Assistant Response: {content}\n")
        else:
            print("\n⚠️ Response structure is different than expected")
            print(f"Keys in response: {list(data.keys())}")
            
    else:
        print("=" * 70)
        print(f"ERROR {response.status_code}")
        print("=" * 70)
        print(response.text)
        
except requests.exceptions.Timeout:
    print("✗ Request timed out after 60 seconds")
    print("This might indicate:")
    print("  - Network connectivity issues")
    print("  - API endpoint is slow or unavailable")
    print("  - Firewall blocking the connection")
    
except requests.exceptions.ConnectionError as e:
    print(f"✗ Connection Error: {e}")
    print("This might indicate:")
    print("  - No internet connection")
    print("  - DNS resolution issues")
    print("  - Firewall blocking HTTPS connections")
    
except Exception as e:
    print(f"✗ Unexpected Error: {type(e).__name__}: {e}")

print("\n" + "=" * 70)
