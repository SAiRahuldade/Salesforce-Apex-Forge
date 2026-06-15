"""Unit tests for NVIDIA NIM API client with mocked requests."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.client import NVIDIANIMClient


class TestNVIDIANIMClient(unittest.TestCase):
    """Test cases for NVIDIANIMClient."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'NVIDIA_API_KEY': 'test-api-key-12345',
            'NVIDIA_API_BASE': 'https://integrate.api.nvidia.com/v1',
            'DEFAULT_MODEL': 'minimaxai/minimax-m3'
        })
        self.env_patcher.start()
        
    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()
    
    def test_client_initialization(self):
        """Test that client initializes correctly with environment variables."""
        client = NVIDIANIMClient()
        
        self.assertEqual(client.api_key, 'test-api-key-12345')
        self.assertEqual(client.api_base, 'https://integrate.api.nvidia.com/v1')
        self.assertEqual(client.model, 'minimaxai/minimax-m3')
        self.assertEqual(
            client.endpoint, 
            'https://integrate.api.nvidia.com/v1/chat/completions'
        )
    
    def test_client_initialization_without_api_key(self):
        """Test that client raises error when API key is missing."""
        with patch.dict(os.environ, {'NVIDIA_API_KEY': ''}, clear=True):
            with self.assertRaises(ValueError) as context:
                NVIDIANIMClient()
            
            self.assertIn('NVIDIA_API_KEY not found', str(context.exception))
    
    @patch('src.client.requests.post')
    def test_non_streaming_chat_completion(self, mock_post):
        """Test non-streaming chat completion with mocked response."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "minimaxai/minimax-m3",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        mock_post.return_value = mock_response
        
        # Create client and make request
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Hello"}]
        result = client.chat_completion(messages, stream=False)
        
        # Verify the request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL
        self.assertEqual(
            call_args[0][0], 
            'https://integrate.api.nvidia.com/v1/chat/completions'
        )
        
        # Check headers
        headers = call_args[1]['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-api-key-12345')
        self.assertEqual(headers['Content-Type'], 'application/json')
        
        # Check payload
        payload = call_args[1]['json']
        self.assertEqual(payload['model'], 'minimaxai/minimax-m3')
        self.assertEqual(payload['messages'], messages)
        self.assertEqual(payload['stream'], False)
        self.assertEqual(payload['temperature'], 0.7)
        
        # Verify response
        self.assertEqual(result['content'], "Hello! How can I help you today?")
        self.assertEqual(result['model'], "minimaxai/minimax-m3")
        self.assertIn('usage', result)
    
    @patch('src.client.requests.post')
    def test_streaming_chat_completion(self, mock_post):
        """Test streaming chat completion with mocked response."""
        # Mock streaming response
        mock_response = Mock()
        mock_response.status_code = 200
        
        # Simulate SSE stream
        stream_data = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            b'data: {"choices":[{"delta":{"content":" there"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"!"}}]}\n',
            b'data: [DONE]\n'
        ]
        mock_response.iter_lines.return_value = stream_data
        mock_post.return_value = mock_response
        
        # Create client and make request
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Hi"}]
        result = client.chat_completion(messages, stream=True)
        
        # Verify the request
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check payload has stream=True
        payload = call_args[1]['json']
        self.assertEqual(payload['stream'], True)
        
        # Collect streamed chunks
        chunks = list(result)
        self.assertEqual(chunks, ["Hello", " there", "!"])
    
    @patch('src.client.requests.post')
    def test_invalid_api_key_error(self, mock_post):
        """Test handling of 401 unauthorized error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        
        with self.assertRaises(ValueError) as context:
            client.chat_completion(messages)
        
        self.assertIn('Invalid API key', str(context.exception))
    
    @patch('src.client.requests.post')
    def test_rate_limit_error(self, mock_post):
        """Test handling of 429 rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        
        with self.assertRaises(ValueError) as context:
            client.chat_completion(messages)
        
        self.assertIn('Rate limit exceeded', str(context.exception))
    
    @patch('src.client.requests.post')
    def test_network_error(self, mock_post):
        """Test handling of network connection errors."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Network error")
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        
        with self.assertRaises(ValueError) as context:
            client.chat_completion(messages)
        
        self.assertIn('Network error', str(context.exception))
    
    @patch('src.client.requests.post')
    def test_timeout_error(self, mock_post):
        """Test handling of request timeout."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        
        with self.assertRaises(ValueError) as context:
            client.chat_completion(messages)
        
        self.assertIn('timed out', str(context.exception))
    
    @patch('src.client.requests.post')
    def test_malformed_response(self, mock_post):
        """Test handling of malformed JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_post.return_value = mock_response
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        
        with self.assertRaises(ValueError) as context:
            client.chat_completion(messages)
        
        self.assertIn('Invalid JSON', str(context.exception))
    
    @patch('src.client.requests.post')
    def test_payload_with_max_tokens(self, mock_post):
        """Test that max_tokens is included in payload when specified."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"role": "assistant", "content": "Test response"}
            }]
        }
        mock_post.return_value = mock_response
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        client.chat_completion(messages, max_tokens=100)
        
        # Verify max_tokens in payload
        payload = mock_post.call_args[1]['json']
        self.assertEqual(payload['max_tokens'], 100)
    
    @patch('src.client.requests.post')
    def test_custom_temperature(self, mock_post):
        """Test that custom temperature is used in payload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"role": "assistant", "content": "Test response"}
            }]
        }
        mock_post.return_value = mock_response
        
        client = NVIDIANIMClient()
        messages = [{"role": "user", "content": "Test"}]
        client.chat_completion(messages, temperature=0.5)
        
        # Verify temperature in payload
        payload = mock_post.call_args[1]['json']
        self.assertEqual(payload['temperature'], 0.5)


def run_tests():
    """Run all tests."""
    unittest.main(argv=[''], verbosity=2, exit=False)


if __name__ == '__main__':
    print("=" * 70)
    print("Running NVIDIA NIM Client Tests")
    print("=" * 70)
    run_tests()
