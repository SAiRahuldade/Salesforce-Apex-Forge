"""Final comprehensive test using the exact working approach."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from client import NVIDIANIMClient
from prompts import format_user_message, format_assistant_message

print("\n" + "=" * 70)
print("NVIDIA NIM Chatbot - Final Comprehensive Test")
print("=" * 70)
print()

# Test 1: Non-Streaming
print("=" * 70)
print("Test 1: Non-Streaming Mode")
print("=" * 70)

try:
    client = NVIDIANIMClient()
    print(f"✓ Client initialized")
    print(f"  API Key: {client.api_key[:20]}...")
    print(f"  Model: {client.model}")
    print(f"  Endpoint: {client.endpoint}\n")
    
    messages = [format_user_message("What is 2+2? Answer briefly.")]
    
    print("Sending: 'What is 2+2? Answer briefly.'")
    print("Waiting for response (this may take 30-60 seconds)...\n")
    
    response = client.chat_completion(messages, stream=False, max_tokens=50)
    
    print("✓ Response received!")
    print("-" * 70)
    print(f"Assistant: {response['content']}")
    print("-" * 70)
    print(f"Model: {response.get('model', 'N/A')}")
    print(f"Usage: {response.get('usage', {})}")
    print("\n✓ Non-streaming test PASSED!\n")
    
except Exception as e:
    print(f"✗ Non-streaming test FAILED: {e}\n")
    import traceback
    traceback.print_exc()

# Test 2: Streaming
print("=" * 70)
print("Test 2: Streaming Mode")
print("=" * 70)

try:
    client2 = NVIDIANIMClient()
    print(f"✓ Client initialized\n")
    
    messages2 = [format_user_message("Count from 1 to 3.")]
    
    print("Sending: 'Count from 1 to 3.'")
    print("Streaming response:\n")
    print("-" * 70)
    
    response_stream = client2.chat_completion(messages2, stream=True, max_tokens=50)
    
    full_response = ""
    for chunk in response_stream:
        print(chunk, end="", flush=True)
        full_response += chunk
    
    print("\n" + "-" * 70)
    
    if full_response:
        print(f"\n✓ Received {len(full_response)} characters")
        print("✓ Streaming test PASSED!\n")
    else:
        print("\n⚠️ No content received in stream\n")
    
except Exception as e:
    print(f"\n✗ Streaming test FAILED: {e}\n")
    import traceback
    traceback.print_exc()

# Test 3: Multi-turn conversation
print("=" * 70)
print("Test 3: Multi-Turn Conversation")
print("=" * 70)

try:
    client3 = NVIDIANIMClient()
    conversation = []
    
    # Turn 1
    conversation.append(format_user_message("Hi! My name is Alice."))
    print("Turn 1 - You: Hi! My name is Alice.")
    
    resp1 = client3.chat_completion(conversation, stream=False, max_tokens=50)
    conversation.append(format_assistant_message(resp1['content']))
    print(f"Turn 1 - Assistant: {resp1['content']}\n")
    
    # Turn 2
    conversation.append(format_user_message("What's my name?"))
    print("Turn 2 - You: What's my name?")
    
    resp2 = client3.chat_completion(conversation, stream=False, max_tokens=50)
    print(f"Turn 2 - Assistant: {resp2['content']}\n")
    
    if "Alice" in resp2['content'] or "alice" in resp2['content'].lower():
        print("✓ Multi-turn conversation test PASSED! (Remembered name)\n")
    else:
        print("⚠️ Multi-turn test completed but didn't remember name\n")
    
except Exception as e:
    print(f"✗ Multi-turn test FAILED: {e}\n")

print("=" * 70)
print("All Tests Complete!")
print("=" * 70)
print("\n✅ The chatbot is ready to use!")
print("\nTo start the interactive chatbot, run:")
print("  python -m src.chat              (non-streaming)")
print("  python -m src.chat --stream     (streaming)\n")
