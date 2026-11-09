"""Startup recovery popups are intentionally disabled.
Recovery discovery and choices now belong to the print file browser.
The install hook is retained for compatibility with the existing screen.py.
"""
def install(screen):
    return None
