#!/usr/bin/env python3
from pathlib import Path
import sys

_VENDOR_DIR = Path(__file__).resolve().parent.parent / ".vendor"
if _VENDOR_DIR.exists():
	sys.path.insert(0, str(_VENDOR_DIR))

from .picarx import Picarx
from .version import __version__
