# Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Your API Key
Copy `.env.example` to `.env` and add your NVIDIA API key:
```bash
copy .env.example .env
```

Edit `.env` and replace `nvapi-paste-your-key-here` with your actual NVIDIA API key.

### 3. Run the Chatbot

**Non-streaming mode (default):**
```bash
python -m src.chat
```

**Streaming mode:**
```bash
python -m src.chat --stream
```

## 📝 Example Usage

```
🤖 NVIDIA NIM Chatbot (minimaxai/minimax-m3) - non-streaming mode
Type 'exit' to quit or press Ctrl+C

You: What is Python?
Assistant: Python is a high-level, interpreted programming language...

You: exit
Goodbye! 👋
```

## 🧪 Run Tests

```bash
python tests\test_client.py
```

## ✅ All Features Implemented

- ✅ Load NVIDIA_API_KEY from .env (using python-dotenv)
- ✅ Uses model: minimaxai/minimax-m3
- ✅ Support streaming AND non-streaming mode
- ✅ Keep conversation history (multi-turn)
- ✅ Type 'exit' or Ctrl+C to quit
- ✅ Add a --stream CLI flag
- ✅ Handle errors gracefully (bad key, rate limit, network)
- ✅ Comprehensive tests with mocked requests
- ✅ No hardcoded API keys

## 📁 Project Structure

```
nvidia-nim-chat/
├── .env.example          # Environment variables template
├── .gitignore           # Git ignore file
├── requirements.txt     # Python dependencies
├── README.md           # Full documentation
├── QUICKSTART.md       # This file
├── config.yaml         # Continue extension config
├── src/
│   ├── __init__.py     # Package initialization
│   ├── client.py       # API call logic (streaming & non-streaming)
│   ├── chat.py         # CLI chat loop with conversation history
│   └── prompts.py      # System prompts and message formatting
└── tests/
    └── test_client.py  # Unit tests with mocked requests
```

## 🔑 Getting Your NVIDIA API Key

1. Visit [NVIDIA NIM](https://build.nvidia.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Generate a new API key
5. Copy it to your `.env` file

## 💡 Tips

- Use `--stream` flag for real-time streaming responses
- The chatbot maintains conversation history automatically
- Press Ctrl+C anytime to exit gracefully
- All errors are handled with helpful messages

## 🐛 Troubleshooting

**"NVIDIA_API_KEY not found"**
- Make sure you created `.env` file (not `.env.example`)
- Verify the API key is set correctly in `.env`

**"Invalid API key"**
- Check that your API key is valid and active
- Ensure there are no extra spaces in the `.env` file

**"Rate limit exceeded"**
- Wait a few moments and try again
- Consider upgrading your API plan if needed

Enjoy chatting! 🎉
