#!/usr/bin/python3
from pathlib import Path
import sys

_VENDOR_DIR = Path(__file__).resolve().parent.parent / ".vendor"
if (_VENDOR_DIR / "robot_hat" / "__init__.py").is_file():
	sys.path.insert(0, str(_VENDOR_DIR))

_SITE_PACKAGES_311 = Path("/usr/local/lib/python3.11/site-packages")
if _SITE_PACKAGES_311.is_dir():
	sys.path.insert(0, str(_SITE_PACKAGES_311))

from .picarx import Picarx
from .version import __version__
