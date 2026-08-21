"""Application entrypoint.

This module is the target for uvicorn (e.g. ``uvicorn main:app``). It simply
imports and executes the application factory to construct the ASGI app.
"""

from app.factory import create_app

app = create_app()
