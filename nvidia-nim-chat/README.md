# NVIDIA NIM Chat CLI

A Python CLI chatbot that calls the NVIDIA NIM API (OpenAI-compatible) with support for streaming and non-streaming modes.

## Features

- ✅ Load NVIDIA_API_KEY from .env (using python-dotenv)
- ✅ Uses model: minimaxai/minimax-m3
- ✅ Support streaming AND non-streaming mode
- ✅ Keep conversation history (multi-turn)
- ✅ Type 'exit' or Ctrl+C to quit
- ✅ Add a --stream CLI flag
- ✅ Handle errors gracefully (bad key, rate limit, network)
- ✅ Comprehensive tests with mocked requests

## Setup

1. **Clone or download this project**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your API key:**
   - Copy `.env.example` to `.env`
   - Replace `nvapi-paste-your-key-here` with your actual NVIDIA API key

   ```bash
   cp .env.example .env
   # Edit .env and paste your key
   ```

## Usage

### Non-streaming mode (default):
```bash
python -m src.chat
```

### Streaming mode:
```bash
python -m src.chat --stream
```

### Example conversation:
```
🤖 NVIDIA NIM Chatbot (minimaxai/minimax-m3)
Type 'exit' to quit or press Ctrl+C

You: Hello! What can you help me with?
Assistant: I can help you with a wide variety of tasks...

You: exit
Goodbye! 👋
```

## Project Structure

```
nvidia-nim-chat/
├── .env.example          # Environment variables template
├── .gitignore
├── requirements.txt
├── README.md
├── config.yaml           # Continue extension config
├── src/
│   ├── __init__.py
│   ├── client.py         # API call logic
│   ├── chat.py           # CLI chat loop
│   └── prompts.py        # System prompts / helpers
└── tests/
    └── test_client.py    # Unit tests with mocked requests
```

## Running Tests

```bash
python -m pytest tests/
```

Or run the test file directly:
```bash
python tests/test_client.py
```

## Error Handling

The chatbot gracefully handles:
- Invalid API keys
- Rate limiting
- Network errors
- Malformed responses
- Keyboard interrupts (Ctrl+C)

## Environment Variables

- `NVIDIA_API_KEY`: Your NVIDIA API key (required)
- `NVIDIA_API_BASE`: API base URL (default: https://integrate.api.nvidia.com/v1)
- `DEFAULT_MODEL`: Model to use (default: minimaxai/minimax-m3)

## License

MIT
