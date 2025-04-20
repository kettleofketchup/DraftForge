import json

from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from social_core.backends.oauth import BaseOAuth1, BaseOAuth2
from social_django.utils import load_strategy, psa

from .decorators import render_to


from django.shortcuts import render

from rest_framework import viewsets
from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAdminUser
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

# Create your views here.
from social_django.models import (  # fix: skip
    USER_MODEL,
    AbstractUserSocialAuth,
    DjangoStorage,
)


def logout(request):
    """Logs out user"""
    auth_logout(request)
    return redirect("/")


@render_to("home.html")
def home(request):
    """Home view, displays login mechanism"""
    if request.user.is_authenticated:
        return redirect("done")
    return None


@login_required
@render_to("home.html")
def done(request):
    """Login complete view, displays user data"""
    return


@render_to("home.html")
def validation_sent(request):
    """Email validation sent confirmation page"""
    return {
        "validation_sent": True,
        "email": request.session.get("email_validation_address"),
    }


@render_to("home.html")
def require_email(request):
    """Email required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "email_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_country(request):
    """Country required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "country_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_city(request):
    """City required page"""
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "city_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@psa("social:complete")
def ajax_auth(request, backend):
    """AJAX authentication endpoint"""
    if isinstance(request.backend, BaseOAuth1):
        token = {
            "oauth_token": request.REQUEST.get("access_token"),
            "oauth_token_secret": request.REQUEST.get("access_token_secret"),
        }
    elif isinstance(request.backend, BaseOAuth2):
        token = request.REQUEST.get("access_token")
    else:
        raise HttpResponseBadRequest("Wrong backend type")
    user = request.backend.do_auth(token, ajax=True)
    login(request, user)
    data = {"id": user.id, "username": user.username}
    return HttpResponse(json.dumps(data), mimetype="application/json")


from django.contrib.auth.models import User
from .serializers import UserSerializer

from .models import CustomUser


@permission_classes((IsAdminUser,))
class UserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = CustomUser.objects.all()


from .models import CustomUser


@api_view(["GET"])
def current_user(request):
    user = request.user

    return Response(
        {
            "username": user.username,
            "avatarUrl": user.avatarUrl,
            "is_staff": user.is_staff,
        }
    )
