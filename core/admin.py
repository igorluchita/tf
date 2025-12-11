from django.contrib import admin

from .models import CustomerThread, Message, ProductPost, SocialPlatform


@admin.register(SocialPlatform)
class SocialPlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "platform", "is_active", "updated_at")
    list_filter = ("platform", "is_active")
    search_fields = ("name", "page_id")


@admin.register(ProductPost)
class ProductPostAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "scheduled_time", "published_at")
    list_filter = ("status",)
    search_fields = ("title", "caption")
    filter_horizontal = ("platforms",)


@admin.register(CustomerThread)
class CustomerThreadAdmin(admin.ModelAdmin):
    list_display = ("external_customer_id", "social_platform", "last_message_at")
    search_fields = ("external_customer_id", "customer_name")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("thread", "is_incoming", "status", "timestamp")
    list_filter = ("is_incoming", "status")
    search_fields = ("content",)
