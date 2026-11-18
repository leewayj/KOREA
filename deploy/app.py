"""Serve the user application and its API under one public origin."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.main import create_app

api = create_app()

@asynccontextmanager
async def lifespan(app):
    async with api.router.lifespan_context(api):
        yield

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/api', api)
app.mount('/', StaticFiles(directory=Path(os.getenv('KOREA_WEB_DIST', 'library-seat-web/dist')), html=True), name='user-web')
