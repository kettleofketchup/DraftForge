from django.urls import path

from . import views
from .functions.generate import gen_double_elim

urlpatterns = [
    path("gen_double_elim/", gen_double_elim, name="gen_double_elim"),
]
