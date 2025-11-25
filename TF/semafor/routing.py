from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/traffic/', consumers.TrafficConsumer.as_asgi()),
]
