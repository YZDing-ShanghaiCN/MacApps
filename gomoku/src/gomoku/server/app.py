from fastapi import FastAPI

app = FastAPI(title="Gomoku API", version="0.1.0")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "name": "Gomoku",
        "description": "First-stage placeholder API for the Gomoku project.",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
