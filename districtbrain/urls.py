from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("chat.urls")),
]

if settings.GOOGLE_SSO_ENABLED:
    urlpatterns.insert(1, path("accounts/", include("allauth.urls")))

admin.site.site_header = f"District Brain — {settings.DISTRICT_NAME}"
admin.site.site_title = "District Brain"
admin.site.index_title = "Console"
