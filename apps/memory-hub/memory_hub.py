#!/usr/bin/env python3
"""Memory Hub — startpunt. Gebruik: python memory_hub.py [open|serve|install|sync|search|...]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memoryhub.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
