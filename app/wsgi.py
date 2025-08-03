"""Public WSGI entry point for the application."""

from app import create_app

application = create_app()
