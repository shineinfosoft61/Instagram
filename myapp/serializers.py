from rest_framework import serializers


class InstagramDownloadSerializer(serializers.Serializer):
    url = serializers.URLField(required=True)