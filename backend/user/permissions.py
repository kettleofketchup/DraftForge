from django.contrib.auth.models import AnonymousUser

from app.models import CustomUser


def is_site_admin(user: CustomUser | AnonymousUser) -> bool:
    return bool(user.is_authenticated and (user.is_staff or user.is_superuser))
