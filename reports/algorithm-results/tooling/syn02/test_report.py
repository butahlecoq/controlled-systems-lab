#!/usr/bin/env python3
"""Compatibility entry point; maintained reporting code lives under scripts/reports."""
from pathlib import Path as _CompatPath
import sys as _compat_sys
_compat_target = _CompatPath(__file__).resolve().parents[4] / "scripts" / "reports" / 'syn02/test_report.py'
_compat_original_path = _compat_sys.path[:]
_compat_sys.path.insert(0, str(_compat_target.parent))
_compat_original_file = __file__
__file__ = str(_compat_target)
exec(compile(_compat_target.read_bytes(), __file__, "exec"), globals())

__file__ = _compat_original_file

_compat_sys.path[:] = _compat_original_path
