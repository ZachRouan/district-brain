from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.home, name="home"),
    path("c/<int:pk>/", views.conversation_detail, name="conversation"),
    path("ask/", views.ask_view, name="ask"),
    # The only sanctioned way to fetch an original source file; scoped per user.
    path("documents/<int:pk>/download/", views.document_download, name="document_download"),
]
