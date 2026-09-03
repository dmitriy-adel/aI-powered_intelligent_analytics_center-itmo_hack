from django.urls import path

from . import views

app_name = "newsroom"

urlpatterns = [
    path("", views.index, name="index"),
]
