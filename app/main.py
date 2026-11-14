from fastapi import FastAPI

app = FastAPI(
    title="Nova Healix Backend API",
    description="Backend API built with FastAPI",
    version="1.0.0",
)


@app.get("/")
async def root():
    return {
        "message": "Nova Healix backend is running!"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy"
    }