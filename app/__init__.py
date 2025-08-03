from config import Config
from flask import Flask
from flask_apscheduler import APScheduler
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis
import rq
import logging
from logging.handlers import RotatingFileHandler
import os

cors = CORS()
limiter = Limiter(
    key_func=get_remote_address, default_limits=["200 per day", "50 per hour"]
)
scheduler = APScheduler()

class AppFlask(Flask):
    """Custom Flask class to allow for type checking of app.redis and app.task_queue."""

    redis: Redis
    task_queue: rq.Queue
    scheduler: APScheduler

def create_app(config_class=Config):
    app = AppFlask(__name__)
    app.config.from_object(config_class)
    app.scheduler = scheduler
    app.redis = Redis.from_url(app.config["REDIS_URL"])
    app.task_queue = rq.Queue("app-tasks", connection=app.redis)
    with app.app_context():
        cors.init_app(app)
        limiter.init_app(app)
        scheduler.init_app(app)
    
    scheduler.start()

    from app.bbc import bp as bbc_bp
    from app.tasks import scheduled

    # Perform initial load of categories and programmes
    scheduled.reload_categories()
    scheduled.reload_programmes()

    app.register_blueprint(bbc_bp, url_prefix="/api/bbc")
    # Set the rate limit for all routes in the bbc_bp blueprint to 1 per second
    limiter.limit("60 per minute")(bbc_bp)

    # Set the debuging to rotating log files and the log format and settings
    if not app.debug:
        if not os.path.exists("logs"):
            os.mkdir("logs")
        file_handler = RotatingFileHandler(
            "logs/flask_api.log", maxBytes=10240, backupCount=10
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info("Flask API startup")

    return app
