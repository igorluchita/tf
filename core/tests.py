import hashlib
import hmac
import json
import time
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from .models import CustomerThread, Message, ProductPost, SocialPlatform
from .tasks import publish_scheduled_posts


@override_settings(TELEGRAM_BOT_TOKEN="test-token")
class PublishScheduledPostsTests(TestCase):
    @mock.patch("core.tasks.TelegramClient.send_message")
    def test_publish_marks_post_as_published(self, send_message):
        platform = SocialPlatform.objects.create(
            name="Telegram Channel",
            platform=SocialPlatform.Platform.TELEGRAM,
            access_token="token",
            page_id="123",
        )
        post = ProductPost.objects.create(
            title="Test",
            caption="Hello world",
            store_link="https://example.com",
            scheduled_time=timezone.now(),
            status=ProductPost.Status.SCHEDULED,
        )
        post.platforms.add(platform)

        publish_scheduled_posts()

        post.refresh_from_db()
        self.assertEqual(post.status, ProductPost.Status.PUBLISHED)
        send_message.assert_called_once()


@override_settings(FACEBOOK_APP_SECRET="fbsecret", WEBHOOK_VERIFY_TOKEN="verify-token")
class WebhookViewTests(TestCase):
    def test_facebook_webhook_persists_message(self):
        SocialPlatform.objects.create(
            name="FB Page",
            platform=SocialPlatform.Platform.FACEBOOK,
            access_token="token",
            page_id="pageid",
        )
        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "user-1"},
                            "message": {"text": "Hello!", "mid": "m1"},
                            "timestamp": int(time.time() * 1000),
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(b"fbsecret", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            "/webhooks/facebook/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CustomerThread.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.first()
        self.assertEqual(message.content, "Hello!")

# Create your tests here.
