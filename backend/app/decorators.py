from functools import wraps

from django.conf import settings
from django.shortcuts import render
from social_django.utils import load_strategy

from common.utils import common_context


def render_to(template):
    """Simple render_to decorator"""

    def decorator(func):
        """Decorator"""

        @wraps(func)
        def wrapper(request, *args, **kwargs):
            """Rendering method"""
            out = func(request, *args, **kwargs) or {}
            if isinstance(out, dict):
                out = render(
                    request,
                    template,
                    common_context(
                        settings.AUTHENTICATION_BACKENDS,
                        load_strategy(),
                        request.user,
                        **out,
                    ),
                )
            return out

        return wrapper

    return decorator
