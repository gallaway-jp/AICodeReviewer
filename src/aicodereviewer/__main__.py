# src/aicodereviewer/__main__.py
"""Allow ``python -m aicodereviewer``."""
import sys

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
