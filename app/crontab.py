"""Crontab configuration for scheduled tasks."""

from flask_crontab import Crontab

class AppCrontab():
    """Custom Crontab class for the application."""

    crontab: Crontab

    def __init__(self, app=None):
        """Initialize the Crontab with the Flask app."""
        self.crontab = Crontab()
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the Crontab with the Flask app."""
        # Additional initialization can be added here if needed.
        self.crontab.init_app(app)

cronservice = AppCrontab()
