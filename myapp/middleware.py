from django.http import JsonResponse
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

from .models import UserSubscription

User = get_user_model()

# Add any path here that requires an active subscription
SUBSCRIPTION_PROTECTED_PATHS = [
    "/api/instagram-download",
    "/api/instagram-private-reel-download",
]


class SubscriptionCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_protected = any(request.path.startswith(p) for p in SUBSCRIPTION_PROTECTED_PATHS)

        if not is_protected:
            return self.get_response(request)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return JsonResponse(
                {"status": "error", "message": "Authentication required."},
                status=401,
            )

        token_str = auth_header.split(" ")[1]
        try:
            token = AccessToken(token_str)
            user_id = token["user_id"]
            user = User.objects.get(id=user_id)
        except (InvalidToken, TokenError, User.DoesNotExist):
            return JsonResponse(
                {"status": "error", "message": "Invalid or expired token."},
                status=401,
            )

        active_sub = (
            UserSubscription.objects.filter(user=user, status="active")
            .order_by("-started_at")
            .first()
        )

        if not active_sub:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "No active subscription. Please purchase a plan.",
                },
                status=403,
            )

        if active_sub.is_expired():
            active_sub.status = "expired"
            active_sub.save()
            self._activate_next_queued(user)
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Your plan has expired. Please renew your subscription.",
                },
                status=403,
            )

        return self.get_response(request)

    def _activate_next_queued(self, user):
        queued_sub = (
            UserSubscription.objects.filter(user=user, status="queued")
            .order_by("created_at")
            .first()
        )

        if queued_sub:
            now = timezone.now()
            queued_sub.status = "active"
            queued_sub.started_at = now
            queued_sub.expires_at = now + timezone.timedelta(days=queued_sub.product.duration_days)
            queued_sub.save()
