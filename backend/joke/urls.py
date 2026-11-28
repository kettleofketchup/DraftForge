from django.urls import URLPattern, path

from joke.views import buy_tango, get_tangoes

urlpatterns: list[URLPattern] = [
    path("tangoes/", get_tangoes, name="get-tangoes"),
    path("tangoes/buy/", buy_tango, name="buy-tango"),
]
