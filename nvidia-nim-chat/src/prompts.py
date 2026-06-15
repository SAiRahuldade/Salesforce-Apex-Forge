"""System prompts and helper functions for the chatbot."""

DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant powered by NVIDIA NIM API.
You provide clear, accurate, and helpful responses to user questions.
Be concise but thorough in your answers."""


def get_system_message():
    """Return the default system message for the chatbot."""
    return {
        "role": "system",
        "content": DEFAULT_SYSTEM_PROMPT
    }


def format_user_message(content: str):
    """Format a user message."""
    return {
        "role": "user",
        "content": content
    }


def format_assistant_message(content: str):
    """Format an assistant message."""
    return {
        "role": "assistant",
        "content": content
    }
