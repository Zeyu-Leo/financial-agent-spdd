"""FastAPI application entrypoint. Task 0: health probe only."""

from fastapi import FastAPI

app = FastAPI(title="Financial Helpdesk Agent", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
