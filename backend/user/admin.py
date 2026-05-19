from django.contrib import admin

from .models import BaseUserProfile


@admin.register(BaseUserProfile)
class BaseUserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nickname", "avatar")
    search_fields = ("user__username", "nickname")
    raw_id_fields = ("user",)
