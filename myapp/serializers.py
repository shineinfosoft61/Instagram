from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from .models import OTPVerification


class InstagramDownloadSerializer(serializers.Serializer):
    url = serializers.URLField(required=True)


CustomUser = get_user_model()


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

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
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        email = attrs.get("email")
        otp = attrs.get("otp")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")

        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

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