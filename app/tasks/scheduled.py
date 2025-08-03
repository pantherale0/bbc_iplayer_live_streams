"""Scheduled tasks for Flask-Crontab."""

from app import scheduler

@scheduler.task('cron', id='reload_categories', minute="0", hour="0")  # Every day at midnight
def reload_categories():
    """Reload categories from the BBC iPlayer."""
    from app.bbc import reload_categories
    reload_categories()

@scheduler.task('interval', id='reload_programmes', misfire_grace_time=600, minutes=30)  # Every 30 minutes
def reload_programmes():
    """Reload programmes from the BBC iPlayer."""
    from app.bbc import reload_programmes
    reload_programmes()

@scheduler.task('interval', id='clear_streams_cache', misfire_grace_time=600, minutes=5)  # Every 5 minutes
def clear_streams_cache():
    """Clear the streams cache."""
    from app.bbc import _STREAMS
    _STREAMS.clear()
