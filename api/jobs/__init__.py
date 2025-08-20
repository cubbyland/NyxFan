# NyxFan/api/jobs/__init__.py
"""
Background jobs for NyxFan.
Currently only the fan-side dash refresh consumer.
"""

from .refresh import process_fan_queue

__all__ = ["process_fan_queue"]
