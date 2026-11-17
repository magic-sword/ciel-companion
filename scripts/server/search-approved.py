#!/usr/bin/env python3
"""CLI for the reviewed API collector used by the conversation service."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server/agent'))
from approved_search import main
if __name__ == '__main__':
    sys.exit(main())
