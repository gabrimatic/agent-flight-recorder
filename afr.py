#!/usr/bin/env python3
"""Repository-local entrypoint for Agent Flight Recorder.

This lets the GitHub Action run without needing a package install, and it lets
contributors run the CLI from a checkout with:

    python afr.py doctor
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from agent_flight_recorder.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
