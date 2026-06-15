"""Live test of the NVIDIA NIM chatbot with real API calls."""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from client import NVIDIANIMClient
from prompts import format_user_message, get_system_message

def test_non_streaming():
    """Test non-streaming mode."""
    print("=" * 70)
    print("Testing Non-Streaming Mode")
    print("=" * 70)
    
    try:
        client = NVIDIANIMClient()
        print(f"✓ Client initialized successfully")
        print(f"  Model: {client.model}")
        print(f"  Endpoint: {client.endpoint}")
        print()
        
        # Test message (without system message for compatibility)
        messages = [
            format_user_message("Hello! Can you tell me what 2+2 equals?")
        ]
        
        print("Sending message: 'Hello! Can you tell me what 2+2 equals?'")
        print("Waiting for response...\n")
        
        response = client.chat_completion(messages, stream=False)
        
        print("Response received:")
        print("-" * 70)
        print(response['content'])
        print("-" * 70)
        print(f"\nModel: {response.get('model', 'N/A')}")
        print(f"Usage: {response.get('usage', {})}")
        print("\n✓ Non-streaming test PASSED!\n")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Non-streaming test FAILED: {e}\n")
        return False


def test_streaming():
    """Test streaming mode."""
    print("=" * 70)
    print("Testing Streaming Mode")
    print("=" * 70)
    
    try:
        client = NVIDIANIMClient()
        print(f"✓ Client initialized successfully")
        print()
        
        # Test message (without system message for compatibility)
        messages = [
            format_user_message("Count from 1 to 5.")
        ]
        
        print("Sending message: 'Count from 1 to 5.'")
        print("Streaming response:\n")
        print("-" * 70)
        
        response_stream = client.chat_completion(messages, stream=True)
        
        full_response = ""
        for chunk in response_stream:
            print(chunk, end="", flush=True)
            full_response += chunk
        
        print("\n" + "-" * 70)
        print(f"\nFull response length: {len(full_response)} characters")
        print("\n✓ Streaming test PASSED!\n")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Streaming test FAILED: {e}\n")
        return False


def main():
    """Run all live tests."""
    print("\n" + "=" * 70)
    print("NVIDIA NIM Chatbot - Live API Tests")
    print("=" * 70)
    print()
    
    results = []
    
    # Test non-streaming
    results.append(("Non-Streaming", test_non_streaming()))
    
    # Test streaming
    results.append(("Streaming", test_streaming()))
    
    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    print("=" * 70)
    
    if all_passed:
        print("\n🎉 All tests passed! The chatbot is working correctly.\n")
    else:
        print("\n⚠️ Some tests failed. Please check the errors above.\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
