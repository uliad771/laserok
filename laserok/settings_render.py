import os

import dj_database_url

from .settings import *


DEBUG = False

# На Render эта переменная должна быть задана.
SECRET_KEY = os.environ["SECRET_KEY"]

render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")

ALLOWED_HOSTS = [
    host
    for host in [
        render_hostname,
        *os.environ.get("EXTRA_ALLOWED_HOSTS", "").split(","),
    ]
    if host
]

CSRF_TRUSTED_ORIGINS = [
    f"https://{host}"
    for host in ALLOWED_HOSTS
]

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=0,
        ssl_require=True,
    )
}

# Убираем channel_binding — psycopg v3 на Windows/Neon рвёт соединение с ним
DATABASES["default"].setdefault("OPTIONS", {}).pop("channel_binding", None)

DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Подключаем WhiteNoise сразу после SecurityMiddleware.
MIDDLEWARE = [
    item
    for item in MIDDLEWARE
    if item != "whitenoise.middleware.WhiteNoiseMiddleware"
]

security_index = MIDDLEWARE.index(
    "django.middleware.security.SecurityMiddleware"
)

MIDDLEWARE.insert(
    security_index + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

STORAGES = {
    **globals().get("STORAGES", {}),
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedStaticFilesStorage"
        ),
    },
}

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True