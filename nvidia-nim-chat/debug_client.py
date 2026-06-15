"""Debug the client to see what's happening."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from client import NVIDIANIMClient
from prompts import format_user_message, get_system_message
import json

print("=" * 70)
print("Debugging Client Response Parsing")
print("=" * 70)

try:
    client = NVIDIANIMClient()
    print(f"✓ Client initialized")
    print(f"  Model: {client.model}")
    print(f"  Endpoint: {client.endpoint}\n")
    
    messages = [
        get_system_message(),
        format_user_message("Say hello")
    ]
    
    print("Sending request...")
    print(f"Messages: {json.dumps(messages, indent=2)}\n")
    
    # Patch the _parse_response to see what we get
    import requests
    
    payload = {
        "model": client.model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False
    }
    
    response = requests.post(
        client.endpoint,
        headers=client._get_headers(),
        json=payload,
        timeout=120
    )
    
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        data = response.json()
        print("Full Response:")
        print("=" * 70)
        print(json.dumps(data, indent=2))
        print("=" * 70)
        
        print("\nParsing response...")
        if "choices" in data:
            print(f"✓ 'choices' found: {len(data['choices'])} choices")
            if len(data["choices"]) > 0:
                print(f"✓ First choice exists")
                choice = data["choices"][0]
                print(f"  Choice keys: {list(choice.keys())}")
                if "message" in choice:
                    print(f"✓ 'message' found")
                    message = choice["message"]
                    print(f"  Message keys: {list(message.keys())}")
                    if "content" in message:
                        print(f"✓ 'content' found: {message['content']}")
                    else:
                        print(f"✗ 'content' NOT found in message")
                else:
                    print(f"✗ 'message' NOT found in choice")
        else:
            print(f"✗ 'choices' NOT found in response")
            print(f"  Response keys: {list(data.keys())}")
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"\n✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
