
import os
from config import Config
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi_amis_admin.admin.settings import Settings
from fastapi_amis_admin.admin.site import AdminSite
from fastapi_amis_admin import i18n
from fastapi.middleware.cors import CORSMiddleware
from fastapi_scheduler import SchedulerAdmin
from fastapi_scheduler.admin import BaseScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

scheduler: BaseScheduler
site: AdminSite
limiter: Limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app_path = __file__.rsplit("/", 1)[0]
data_path = f"{app_path}/data"


class FastAPIApp(FastAPI):
    """Custom FastAPI application."""

    site: AdminSite
    scheduler: BaseScheduler
    limiter: Limiter

@asynccontextmanager
async def lifespan(app: FastAPIApp):
    """Lifespan context manager for FastAPI."""
    from app.tasks import scheduled
    # Perform initial data load
    await scheduled.reload_categories()
    await scheduled.reload_programmes()
    app.scheduler.start()
    yield
    app.scheduler.shutdown()


def create_fastapi(config_class=Config):
    """Create a FastAPI application."""
    global scheduler
    app = FastAPIApp(lifespan=lifespan)
    i18n.set_language("en_US")
    app.site = site = AdminSite(
        settings=Settings(
            database_url_async=config_class.SQLALCHEMY_DATABASE_URI,
            language="en_US",
            amis_cdn="https://cdn.jsdelivr.net/npm"))
    app.scheduler = SchedulerAdmin.bind(app.site)
    scheduler = app.scheduler
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    from app.bbc import bp as bbc_bp
    from app.bbc.admin import BBCAdmin
    BBCAdmin.bind(app.site)
    app.include_router(bbc_bp)
    app.site.mount_app(app)

    return app
