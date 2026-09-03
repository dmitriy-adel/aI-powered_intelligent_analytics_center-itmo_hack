from django.urls import path

from . import views

app_name = "newsroom"

urlpatterns = [
    path("", views.index, name="index"),

    path("get_sources", views.get_sources, name="get_sources"),
    path("add_source", views.add_source, name="add_source"),
    path("change_source", views.change_source, name="change_source"),
    path("remove_source", views.remove_source, name="remove_source"),

    path("get_news", views.get_news, name="get_news"),
    path("add_news", views.add_news, name="add_news"),
    path("change_news", views.change_news, name="change_news"),
    path("remove_news", views.remove_news, name="remove_news"),
]
