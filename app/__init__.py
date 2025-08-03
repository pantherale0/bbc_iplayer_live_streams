from config import Config
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi_amis_admin.admin.settings import Settings
from fastapi_amis_admin.admin.site import AdminSite
from fastapi.middleware.cors import CORSMiddleware
from fastapi_scheduler import SchedulerAdmin
from fastapi_scheduler.admin import BaseScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

scheduler: BaseScheduler
limiter: Limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Lifespan context manager for FastAPI."""
    from app.tasks import scheduled
    # Perform initial data load
    await scheduled.reload_categories()
    await scheduled.reload_programmes()
    yield

def create_fastapi(config_class=Config):
    """Create a FastAPI application."""
    global scheduler
    app = FastAPI(lifespan=lifespan)
    site = AdminSite(settings=Settings(database_url_async=config_class.SQLALCHEMY_DATABASE_URI))
    scheduler = SchedulerAdmin.bind(site)
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

    app.include_router(bbc_bp)

    return app
