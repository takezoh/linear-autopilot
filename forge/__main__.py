import sys
from .orchestrator import main

sys.exit(0 if main() else 1)
