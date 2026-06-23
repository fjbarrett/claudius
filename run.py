#!/usr/bin/env python3
"""Convenience launcher: `python3 run.py --task ...` (same as `python3 -m claudius`)."""
import sys

from claudius.cli import main

if __name__ == "__main__":
    sys.exit(main())
