from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from .models import OTPVerification, StripeProduct, UserSubscription


class InstagramDownloadSerializer(serializers.Serializer):
    url = serializers.URLField(required=True)


CustomUser = get_user_model()


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        name = validated_data.get("name")
        email = validated_data.get("email")
        password = validated_data.get("password")
        user = CustomUser.objects.create_user(email=email, name=name, password=password)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        attrs["user"] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        email = attrs.get("email")
        otp = attrs.get("otp")

        try:
            user = CustomUser.objects.get(email__iexact=email)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist."})

        try:
            otp_obj = OTPVerification.objects.get(user=user, otp=otp)
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError({"otp": "Invalid OTP."})

        if otp_obj.is_expired():
            raise serializers.ValidationError({"otp": "OTP has expired."})

        attrs["user"] = user
        attrs["otp_obj"] = otp_obj
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class CreateProductSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(required=True, max_digits=10, decimal_places=2)
    currency = serializers.CharField(required=False, default="usd")
    plan_type = serializers.ChoiceField(
        choices=["weekly", "monthly", "yearly", "custom"],
        required=True,
    )
    duration_days = serializers.IntegerField(required=True, min_value=1)


class CreatePaymentIntentSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)


class PaymentStatusSerializer(serializers.Serializer):
    stripe_payment_intent_id = serializers.CharField(required=True)


class PlanListSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeProduct
        fields = [
            "id",
            "name",
            "description",
            "amount",
            "currency",
            "plan_type",
            "duration_days",
            "stripe_price_id",
        ]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="product.name", read_only=True)
    plan_type = serializers.CharField(source="product.plan_type", read_only=True)
    amount = serializers.DecimalField(
        source="product.amount", max_digits=10, decimal_places=2, read_only=True
    )
    currency = serializers.CharField(source="product.currency", read_only=True)

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "status",
            "plan_name",
            "plan_type",
            "amount",
            "currency",
            "started_at",
            "expires_at",
        ]