"""Run unit tests with real network connections prohibited, including localhost.

Usage: python tests/run_isolated.py [test_filename_pattern]
Never run printer validation suites against a live controller without isolation.
"""
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def blocked(*args, **kwargs):
    raise AssertionError('Real network access is forbidden in unit tests; mock the transport')


def main():
    folder=Path(__file__).resolve().parent
    with patch.object(socket.socket, 'connect', blocked), \
         patch.object(socket.socket, 'connect_ex', blocked), \
         patch.object(socket, 'create_connection', blocked):
        suite=unittest.defaultTestLoader.discover(str(folder), pattern=sys.argv[1] if len(sys.argv)>1 else 'test_*.py')
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
