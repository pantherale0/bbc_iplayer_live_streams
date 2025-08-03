"""Public ASGI entry point for the application."""

from app import create_fastapi

application = create_fastapi()
