"""Local synthetic demo, isolated from db.sqlite3 and DATABASE_URL."""

from .settings import *  # noqa: F403
from .settings import BASE_DIR

DEBUG = True
SECRET_KEY = "local-demo-only-not-for-deployment-00000000000000000000000000000000"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "bloodlink-demo.sqlite3",
    }
}
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
BLOODLINK_DEMO = True
