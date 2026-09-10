import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="ZeroOps Demo Application", version="1.0.0")

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")


@app.get("/")
def read_root():
    return {
        "app": "ZeroOps Demo",
        "version": APP_VERSION,
        "status": "running",
        "message": "Deployed automatically via ZeroOps AI pipeline",
    }


@app.get("/health")
def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "code": 200, "version": APP_VERSION},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
