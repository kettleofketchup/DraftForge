"""
ASGI config for backend project.

Exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Safe to call more than once; later calls are no-ops
from telemetry.config import init_telemetry  # noqa: E402
from telemetry.diagnostics import install_thread_dump_handler  # noqa: E402

init_telemetry()

# `docker kill -s USR1 <backend>` dumps all thread stacks to the container log
install_thread_dump_handler()

# Import routing after Django and telemetry are initialized
import app.routing  # noqa: E402
import draft.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    [
                        *app.routing.websocket_urlpatterns,
                        *draft.routing.websocket_urlpatterns,
                    ]
                )
            )
        ),
    }
)
