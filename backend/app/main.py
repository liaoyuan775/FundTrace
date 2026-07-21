from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .ai.qwen import QwenAdapter
from .api.routes import router as api_router
from .config import Settings, get_settings
from .repository.file_repo import FileRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    repo = FileRepository(settings.data_dir)
    app = FastAPI(title="FundTrace API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.repo = repo
    app.state.qwen = QwenAdapter(settings)

    # Health check
    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "storage": "files",
            "model": app.state.qwen.probe().model_dump(),
        }

    # Register API routes
    app.include_router(api_router)

    # Serve frontend static files if built
    frontend_dist = (
        Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    if frontend_dist.exists():
        app.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )

    return app


app = create_app()
