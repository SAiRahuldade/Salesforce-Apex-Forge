#!/usr/bin/env python
"""Entry point for the AI Agent - can be run directly"""

import sys
import os

# Add nvidia-nim-chat to path for direct execution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)

# Now import and run
from src.agent import main

if __name__ == "__main__":
    main()
