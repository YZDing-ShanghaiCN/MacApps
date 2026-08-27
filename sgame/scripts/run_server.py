import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "sgame.server.app:app",
        host=os.getenv("SGAME_HOST", "127.0.0.1"),
        port=int(os.getenv("SGAME_PORT", "8001")),
    )
