import datetime as dt
import hashlib
import hmac
import time
from typing import List, Optional

import requests
from django.utils import timezone

from . import TokenExpiredError


class FacebookClient:
    base_url = "https://graph.facebook.com/v19.0"

    def __init__(self, access_token: str, app_secret: str, page_id: Optional[str] = None):
        self.access_token = access_token
        self.app_secret = app_secret
        self.page_id = page_id

    def _request(self, url: str, data: dict):
        response = requests.post(url, data=data, timeout=10)
        if response.status_code in (401, 403):
            raise TokenExpiredError("Facebook token expired or invalid")
        response.raise_for_status()
        return response.json()

    def publish_post(self, caption: str, link: Optional[str] = None, media_url: Optional[str] = None):
        if not self.page_id:
            raise ValueError("Facebook page id is required to publish posts")

        endpoint = f"{self.base_url}/{self.page_id}/photos" if media_url else f"{self.base_url}/{self.page_id}/feed"
        payload = {"message": caption, "access_token": self.access_token}
        if link:
            payload["link"] = link
        if media_url:
            payload["url"] = media_url
        return self._request(endpoint, payload)

    @staticmethod
    def parse_webhook_payload(payload: dict) -> List[dict]:
        events: List[dict] = []
        for entry in payload.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender = messaging_event.get("sender", {})
                message = messaging_event.get("message", {})
                timestamp_ms = messaging_event.get("timestamp", int(time.time() * 1000))
                events.append(
                    {
                        "external_customer_id": sender.get("id"),
                        "customer_name": sender.get("name", ""),
                        "content": message.get("text") or "",
                        "timestamp": dt.datetime.fromtimestamp(
                            timestamp_ms / 1000, tz=dt.timezone.utc
                        ),
                        "external_message_id": message.get("mid"),
                        "is_incoming": True,
                    }
                )
        return events

    def verify_signature(self, payload: bytes, header_signature: str) -> bool:
        if not header_signature:
            return False
        try:
            method, provided_signature = header_signature.split("=")
        except ValueError:
            return False
        if method != "sha256":
            return False
        expected = hmac.new(
            self.app_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, provided_signature)
