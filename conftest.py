"""Root conftest.py — ensures the project root is on sys.path for all tests."""

import sys
from pathlib import Path

# Add project root to path so `import backend` works from any test
sys.path.insert(0, str(Path(__file__).parent))
