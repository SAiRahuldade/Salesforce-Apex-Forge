"""CLI chat interface for NVIDIA NIM chatbot."""

import sys
import argparse
from typing import List, Dict
from .client import NVIDIANIMClient
from .prompts import get_system_message, format_user_message, format_assistant_message


class ChatBot:
    """Interactive chatbot CLI."""
    
    def __init__(self, stream: bool = False):
        """
        Initialize the chatbot.
        
        Args:
            stream: Whether to use streaming mode
        """
        self.stream = stream
        self.client = None
        self.conversation_history: List[Dict[str, str]] = []
        
    def initialize(self):
        """Initialize the API client."""
        try:
            self.client = NVIDIANIMClient()
            # Note: System message can be added but some models may not support it
            # Uncomment the line below if you want to use a system message:
            # self.conversation_history.append(get_system_message())
            return True
        except ValueError as e:
            print(f"❌ Error: {e}")
            return False
    
    def print_welcome(self):
        """Print welcome message."""
        mode = "streaming" if self.stream else "non-streaming"
        print(f"\n🤖 NVIDIA NIM Chatbot ({self.client.model}) - {mode} mode")
        print("Type 'exit' to quit or press Ctrl+C\n")
    
    def get_user_input(self) -> str:
        """Get input from the user."""
        try:
            return input("You: ").strip()
        except EOFError:
            return "exit"
    
    def send_message(self, user_message: str):
        """
        Send a message and get response.
        
        Args:
            user_message: The user's message
        """
        # Add user message to history
        self.conversation_history.append(format_user_message(user_message))
        
        try:
            if self.stream:
                self._handle_streaming_response()
            else:
                self._handle_non_streaming_response()
                
        except ValueError as e:
            print(f"\n❌ Error: {e}\n")
            # Remove the failed user message from history
            self.conversation_history.pop()
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}\n")
            self.conversation_history.pop()
    
    def _handle_streaming_response(self):
        """Handle streaming response from API."""
        print("Assistant: ", end="", flush=True)
        
        full_response = ""
        try:
            response_stream = self.client.chat_completion(
                messages=self.conversation_history,
                stream=True
            )
            
            for chunk in response_stream:
                print(chunk, end="", flush=True)
                full_response += chunk
            
            print("\n")  # New line after response
            
            # Add assistant response to history
            if full_response:
                self.conversation_history.append(
                    format_assistant_message(full_response)
                )
                
        except Exception as e:
            print(f"\n❌ Streaming error: {e}\n")
            raise
    
    def _handle_non_streaming_response(self):
        """Handle non-streaming response from API."""
        response = self.client.chat_completion(
            messages=self.conversation_history,
            stream=False
        )
        
        assistant_message = response["content"]
        print(f"Assistant: {assistant_message}\n")
        
        # Add assistant response to history
        self.conversation_history.append(
            format_assistant_message(assistant_message)
        )
    
    def run(self):
        """Run the chat loop."""
        if not self.initialize():
            return
        
        self.print_welcome()
        
        try:
            while True:
                user_input = self.get_user_input()
                
                # Check for exit command
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye! 👋")
                    break
                
                # Skip empty input
                if not user_input:
                    continue
                
                # Send message and get response
                self.send_message(user_input)
                
        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋")
        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            sys.exit(1)


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="NVIDIA NIM Chat CLI - Interactive chatbot"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Enable streaming mode for responses"
    )
    
    args = parser.parse_args()
    
    chatbot = ChatBot(stream=args.stream)
    chatbot.run()


if __name__ == "__main__":
    main()
