from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "user_count", "document_count")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Users")
    def user_count(self, obj):
        return obj.users.count()

    @admin.display(description="Documents scoped to this role")
    def document_count(self, obj):
        return obj.documents.count()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (("District Brain", {"fields": ("role",)}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (("District Brain", {"fields": ("role",)}),)
