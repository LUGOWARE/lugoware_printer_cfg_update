#!/usr/bin/python3
"""Isolated entry point installed root-owned, outside the user's Python paths."""
import sys

sys.path.insert(0, '/opt/lugoware/update-runtime')
from channel_worker import run

if __name__ == '__main__':
    run(sys.argv[1])
