from fastapi import Request

from ..ai.qwen import QwenAdapter
from ..config import Settings
from ..repository.file_repo import FileRepository


def get_repo(request: Request) -> FileRepository:
    return request.app.state.repo


def get_qwen(request: Request) -> QwenAdapter:
    return request.app.state.qwen


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
