"""Make `core.*` / `database.*` importable when pytest runs from the repo
root (backend modules import each other as top-level packages, assuming
the backend/ directory is the working directory)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
