import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "gomoku.server.app:app",
        host=os.getenv("GOMOKU_HOST", "127.0.0.1"),
        port=int(os.getenv("GOMOKU_PORT", "8000")),
    )
