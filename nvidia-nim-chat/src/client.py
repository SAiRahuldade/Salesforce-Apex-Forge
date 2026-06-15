"""NVIDIA NIM API client with streaming and non-streaming support."""

import os
import json
import requests
from typing import List, Dict, Iterator, Optional
from dotenv import load_dotenv


class NVIDIANIMClient:
    """Client for interacting with NVIDIA NIM API (OpenAI-compatible)."""
    
    def __init__(self):
        """Initialize the client with environment variables."""
        load_dotenv()
        
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError(
                "NVIDIA_API_KEY not found in environment. "
                "Please set it in your .env file."
            )
        
        self.api_base = os.getenv(
            "NVIDIA_API_BASE", 
            "https://integrate.api.nvidia.com/v1"
        )
        self.model = os.getenv("DEFAULT_MODEL", "minimaxai/minimax-m3")
        self.endpoint = f"{self.api_base}/chat/completions"
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict | Iterator[str]:
        """
        Send a chat completion request to NVIDIA NIM API.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            stream: Whether to stream the response
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            
        Returns:
            If stream=False: Dictionary with the complete response
            If stream=True: Iterator yielding response chunks
            
        Raises:
            requests.exceptions.RequestException: For network errors
            ValueError: For invalid API responses
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        else:
            # Set a reasonable default to avoid empty responses
            payload["max_tokens"] = 1024
        
        try:
            response = requests.post(
                self.endpoint,
                headers=self._get_headers(),
                json=payload,
                stream=stream,
                timeout=120  # Increased timeout for slower API responses
            )
            
            # Handle HTTP errors
            if response.status_code == 401:
                raise ValueError(
                    "Invalid API key. Please check your NVIDIA_API_KEY in .env"
                )
            elif response.status_code == 429:
                raise ValueError(
                    "Rate limit exceeded. Please try again later."
                )
            elif response.status_code >= 400:
                error_msg = f"API error ({response.status_code})"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error']}"
                except:
                    error_msg += f": {response.text}"
                raise ValueError(error_msg)
            
            if stream:
                return self._stream_response(response)
            else:
                return self._parse_response(response)
                
        except requests.exceptions.Timeout:
            raise ValueError("Request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            raise ValueError(
                "Network error. Please check your internet connection."
            )
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Request failed: {str(e)}")
    
    def _parse_response(self, response: requests.Response) -> Dict:
        """Parse a non-streaming response."""
        try:
            data = response.json()
            
            # Check if response has choices
            if "choices" not in data:
                raise ValueError(f"Invalid response format: no 'choices' field. Response keys: {list(data.keys())}")
            
            if len(data["choices"]) == 0:
                raise ValueError(f"Invalid response format: empty choices array. Full response: {json.dumps(data)}")
            
            # Extract the message content
            choice = data["choices"][0]
            if "message" not in choice:
                raise ValueError(f"Invalid response format: no 'message' in choice. Choice keys: {list(choice.keys())}")
            
            message = choice["message"]
            if "content" not in message:
                raise ValueError(f"Invalid response format: no 'content' in message. Message keys: {list(message.keys())}")
            
            return {
                "content": message["content"],
                "model": data.get("model", self.model),
                "usage": data.get("usage", {})
            }
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON response from API")
        except (KeyError, IndexError) as e:
            raise ValueError(f"Unexpected response format: {str(e)}")
    
    def _stream_response(self, response: requests.Response) -> Iterator[str]:
        """
        Parse a streaming response.
        
        Yields:
            Content chunks from the streaming response
        """
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8')
                
                # Skip empty lines and comments
                if not line.strip() or line.startswith(':'):
                    continue
                
                # Remove 'data: ' prefix
                if line.startswith('data: '):
                    line = line[6:]
                
                # Check for end of stream
                if line.strip() == '[DONE]':
                    break
                
                try:
                    chunk = json.loads(line)
                    
                    # Extract content from the chunk
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                            
                except json.JSONDecodeError:
                    # Skip malformed JSON chunks
                    continue
                    
        except Exception as e:
            raise ValueError(f"Error streaming response: {str(e)}")
