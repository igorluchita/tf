from celery import shared_task
from django.conf import settings
from django.utils import timezone

from integrations import TokenExpiredError
from integrations.facebook_client import FacebookClient
from integrations.instagram_client import InstagramClient
from integrations.telegram_client import TelegramClient

from .models import ProductPost, SocialPlatform


def publish_to_platform(post: ProductPost, platform: SocialPlatform):
    message_body = post.caption
    if post.store_link:
        message_body = f"{message_body}\n{post.store_link}"

    if platform.platform == SocialPlatform.Platform.FACEBOOK:
        client = FacebookClient(
            platform.access_token, settings.FACEBOOK_APP_SECRET, platform.page_id
        )
        client.publish_post(
            caption=message_body,
            link=post.store_link,
            media_url=post.media_url,
        )
    elif platform.platform == SocialPlatform.Platform.INSTAGRAM:
        client = InstagramClient(
            platform.access_token, settings.INSTAGRAM_APP_SECRET, platform.page_id
        )
        if not post.media_url:
            raise ValueError("Instagram publishing requires media_url")
        media = client.create_media_container(caption=message_body, media_url=post.media_url)
        creation_id = media.get("id")
        client.publish_media(creation_id)
    elif platform.platform == SocialPlatform.Platform.TELEGRAM:
        client = TelegramClient(settings.TELEGRAM_BOT_TOKEN or platform.access_token, platform.page_id)
        client.send_message(text=message_body)
    else:
        raise ValueError(f"Unsupported platform {platform.platform}")


@shared_task
def publish_scheduled_posts():
    due_posts = ProductPost.objects.filter(
        status=ProductPost.Status.SCHEDULED, scheduled_time__lte=timezone.now()
    )
    for post in due_posts:
        all_successful = True
        for platform in post.platforms.filter(is_active=True):
            try:
                publish_to_platform(post, platform)
            except TokenExpiredError:
                platform.is_active = False
                platform.save(update_fields=["is_active", "updated_at"])
                all_successful = False
            except Exception:
                all_successful = False
        if all_successful:
            post.mark_published()
        else:
            post.mark_failed()
    return due_posts.count()
