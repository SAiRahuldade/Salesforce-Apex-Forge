# Custom Cline Agent Configuration

## Purpose
This file configures Cline to use your personalized NVIDIA NIM agent with Minimax M3 model as the code editor's AI backend.

## API Configuration
- **Provider**: NVIDIA NIM (OpenAI-compatible)
- **Model**: minimaxai/minimax-m3
- **Base URL**: https://integrate.api.nvidia.com/v1
- **API Key**: Stored in .env (NVIDIA_API_KEY)

## Agent Capabilities
Your personalized agent understands:
- ✅ Full project structure (Salesforce 60-agent platform)
- ✅ Existing codebase patterns and architecture
- ✅ Tool layer integration (10 tools)
- ✅ Workflow engine design
- ✅ Multi-agent orchestration
- ✅ Memory system implementation
- ✅ Reward learning patterns

## Use Cases
1. **Code Generation** - Generate Python code matching your existing patterns
2. **Codebase Analysis** - Understand your 95% complete Salesforce platform
3. **Testing** - Create pytest test suites
4. **Documentation** - Generate comprehensive docs
5. **Debugging** - Find and fix issues using tools
6. **Architecture** - Design new agent components

## Integration
This configuration enables:
- File system access (read/write)
- Shell command execution
- Codebase exploration
- Intelligent tool-based problem solving
