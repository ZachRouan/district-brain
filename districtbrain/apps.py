from django.contrib.admin.apps import AdminConfig


class ConsoleAdminConfig(AdminConfig):
    default_site = "districtbrain.admin.ConsoleAdminSite"
