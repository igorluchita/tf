import hashlib
import hmac
import json

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from integrations.facebook_client import FacebookClient
from integrations.instagram_client import InstagramClient
from integrations.telegram_client import TelegramClient

from .models import CustomerThread, Message, SocialPlatform


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    http_method_names = ["get", "post"]

    def get(self, request, platform: str):
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and token == settings.WEBHOOK_VERIFY_TOKEN:
            return HttpResponse(challenge or "")
        return HttpResponseForbidden("Invalid verification token")

    def post(self, request, platform: str):
        platform_key = platform.lower()
        if not self._verify_signature(platform_key, request):
            return HttpResponseForbidden("Invalid signature")
        payload = self._parse_payload(request.body)
        if payload is None:
            return HttpResponseBadRequest("Invalid payload")
        self._persist_messages(platform_key, payload)
        return JsonResponse({"status": "ok"})

    def _parse_payload(self, body: bytes):
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _verify_signature(self, platform: str, request) -> bool:
        body = request.body
        if platform in ("facebook", "instagram"):
            header = request.headers.get("X-Hub-Signature-256")
            secret = settings.FACEBOOK_APP_SECRET if platform == "facebook" else settings.INSTAGRAM_APP_SECRET
            if not header or not secret:
                return False
            try:
                method, received = header.split("=")
            except ValueError:
                return False
            if method != "sha256":
                return False
            expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, received)
        if platform == "telegram":
            header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            secret = settings.TELEGRAM_BOT_TOKEN
            return bool(header_token and secret and hmac.compare_digest(header_token, secret))
        return False

    def _persist_messages(self, platform: str, payload: dict):
        client = None
        platform_obj = SocialPlatform.objects.filter(platform=platform, is_active=True).first()
        if not platform_obj:
            return
        if platform == "facebook":
            client = FacebookClient(platform_obj.access_token, settings.FACEBOOK_APP_SECRET, platform_obj.page_id)
        elif platform == "instagram":
            client = InstagramClient(
                platform_obj.access_token, settings.INSTAGRAM_APP_SECRET, platform_obj.page_id
            )
        elif platform == "telegram":
            client = TelegramClient(settings.TELEGRAM_BOT_TOKEN or platform_obj.access_token, platform_obj.page_id)

        if not client:
            return

        parser = getattr(client, "parse_webhook_payload", None)
        if not parser:
            return

        events = parser(payload)
        for event in events:
            thread, _ = CustomerThread.objects.get_or_create(
                social_platform=platform_obj,
                external_customer_id=event.get("external_customer_id"),
                defaults={"customer_name": event.get("customer_name", "")},
            )
            thread.customer_name = event.get("customer_name") or thread.customer_name
            thread.save(update_fields=["customer_name", "updated_at"])

            Message.objects.create(
                thread=thread,
                content=event.get("content") or "",
                timestamp=event.get("timestamp") or timezone.now(),
                is_incoming=event.get("is_incoming", True),
                external_message_id=event.get("external_message_id"),
                status=Message.DeliveryStatus.DELIVERED if event.get("is_incoming", True) else Message.DeliveryStatus.SENT,
            )


class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        threads = (
            CustomerThread.objects.select_related("social_platform")
            .prefetch_related("messages")
            .order_by("-last_message_at", "-updated_at")[:50]
        )
        context["threads"] = threads
        return context
