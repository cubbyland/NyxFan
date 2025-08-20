# NyxFan/api/jobs/__init__.py
"""
Background jobs for NyxFan.
Currently exposes the shared queue processor.
"""

from .processor import process_proxy_commands

__all__ = ["process_proxy_commands"]
