"""Double-click launcher (.pyw opens without a console window)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from labelprint.gui import main

if __name__ == "__main__":
    main()
