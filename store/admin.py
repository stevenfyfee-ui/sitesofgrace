from django.contrib import admin

from .models import WaitlistSignup


@admin.register(WaitlistSignup)
class WaitlistSignupAdmin(admin.ModelAdmin):
    list_display = ["email", "product", "created_at"]
    list_filter = ["product"]
    search_fields = ["email"]
    ordering = ["-created_at"]
