from django.db import models
from django.utils import timezone


class SocialPlatform(models.Model):
    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        TELEGRAM = "telegram", "Telegram"

    name = models.CharField(max_length=100)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    access_token = models.CharField(max_length=512)
    refresh_token = models.CharField(max_length=512, blank=True, null=True)
    page_id = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.platform})"


class ProductPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=255, blank=True)
    caption = models.TextField()
    media_url = models.URLField(blank=True, null=True)
    store_link = models.URLField(blank=True, null=True)
    scheduled_time = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    published_at = models.DateTimeField(blank=True, null=True)
    platforms = models.ManyToManyField(SocialPlatform, related_name="posts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_failed(self):
        self.status = self.Status.FAILED
        self.save(update_fields=["status", "updated_at"])

    def mark_published(self):
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"])

    def __str__(self) -> str:
        return self.title or f"Post {self.pk}"


class CustomerThread(models.Model):
    social_platform = models.ForeignKey(
        SocialPlatform, on_delete=models.CASCADE, related_name="threads"
    )
    external_customer_id = models.CharField(max_length=255)
    customer_name = models.CharField(max_length=255, blank=True)
    last_message_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("social_platform", "external_customer_id")

    def __str__(self) -> str:
        return f"{self.external_customer_id} ({self.social_platform.platform})"


class Message(models.Model):
    class DeliveryStatus(models.TextChoices):
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        PENDING = "pending", "Pending"

    thread = models.ForeignKey(
        CustomerThread, related_name="messages", on_delete=models.CASCADE
    )
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    is_incoming = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    external_message_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["timestamp", "id"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.thread_id and (
            not self.thread.last_message_at or self.timestamp >= self.thread.last_message_at
        ):
            CustomerThread.objects.filter(pk=self.thread_id).update(
                last_message_at=self.timestamp, updated_at=timezone.now()
            )

    def __str__(self) -> str:
        direction = "Incoming" if self.is_incoming else "Outgoing"
        return f"{direction} message on {self.thread}"
