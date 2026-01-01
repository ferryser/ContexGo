"""Configuration values for infrastructure-level modules."""

from __future__ import annotations

import platform

is_test_mode: bool = True


def get_sys_type() -> str:
    """Return normalized system type identifier."""
    sys_type = platform.system().strip().lower()
    if sys_type == "windows":
        return "windows"
    if sys_type == "linux":
        return "linux"
    if sys_type == "darwin":
        return "darwin"
    return sys_type
