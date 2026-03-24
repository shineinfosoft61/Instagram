import os
import random
import boto3
import uuid
import shutil
import stripe

from urllib.parse import urlparse
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
import instaloader

import yt_dlp

from .models import OTPVerification, StripeProduct, Payment
from .serializers import (
    InstagramDownloadSerializer,
    RegisterSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    VerifyOTPSerializer,
    LogoutSerializer,
    CreateProductSerializer,
    CreatePaymentIntentSerializer,
    PaymentStatusSerializer,
)


class Ping(APIView):
    def post(self, request):
        return Response({"success": "health is ok"}, status=200)

class InstagramDownloadView(APIView):
    def post(self, request):
        url = request.data.get("url")
        if not url:
            return Response({"error": "URL is required"}, status=400)

        # Create a unique temp folder for every request (fix file conflict issues)
        temp_dir = f"/tmp/social_downloads_{uuid.uuid4().hex}"
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # ----------- Platform Detector ------------
            if "instagram.com" in url:
                uploaded_files = self.download_instagram(url, temp_dir)

            elif any(x in url for x in ["youtube.com", "youtu.be"]):
                uploaded_files = self.download_with_ytdlp(url, temp_dir)

            elif any(x in url for x in ["facebook.com", "fb.watch"]):
                uploaded_files = self.download_with_ytdlp(url, temp_dir)

            elif any(x in url for x in ["whatsapp.com", "wa.me"]):
                uploaded_files = self.download_with_ytdlp(url, temp_dir)

            else:
                return Response({"error": "Unsupported URL platform"}, status=400)

            # Upload all downloaded files to S3
            s3_urls = self.upload_to_s3(uploaded_files, temp_dir)

            return Response({
                "message": "Downloaded Successfully",
                "downloads": s3_urls
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

        finally:
            self.clean_files(temp_dir)

    # ----------- INSTAGRAM DOWNLOAD -----------
    def download_instagram(self, url, temp_dir):
        parsed = urlparse(url)
        shortcode = parsed.path.strip("/").split("/")[-1]

        loader = instaloader.Instaloader(
            dirname_pattern=temp_dir,
            save_metadata=False
        )

        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target=temp_dir)

        files = [f for f in os.listdir(temp_dir) if not f.endswith(".json")]
        return files

    # ----------- YT-DLP DOWNLOAD (YouTube + FB + WhatsApp) -----------
    def download_with_ytdlp(self, url, temp_dir):
        outtmpl = os.path.join(temp_dir, "%(title)s.%(ext)s")

        # -------- FIRST TRY (NO COOKIES) --------
        ydl_opts_no_cookies = {
            "outtmpl": outtmpl,
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",

            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,

            # Anti-bot tuning
            "sleep_interval": 2,
            "max_sleep_interval": 5,
            "retries": 3,
            "source_address": "0.0.0.0",

            # Android client (MOST IMPORTANT)
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                    "skip": ["dash", "hls"]
                }
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts_no_cookies) as ydl:
                ydl.download([url])

            files = os.listdir(temp_dir)
            if files:
                return files

        except Exception as e:
            error_msg = str(e)

            # If NOT bot error → raise immediately
            if "confirm you’re not a bot" not in error_msg.lower():
                raise Exception(error_msg)

        # -------- FALLBACK (WITH COOKIES) --------
        ydl_opts_with_cookies = {
            "outtmpl": outtmpl,
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",

            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,

            "cookiefile": "/home/ronak/cookies.txt",  # ABSOLUTE PATH
        }

        with yt_dlp.YoutubeDL(ydl_opts_with_cookies) as ydl:
            ydl.download([url])

        return os.listdir(temp_dir)


    # ----------- UPLOAD TO S3 -----------
    def upload_to_s3(self, files, temp_dir):
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

        uploaded_urls = []

        for file in files:
            local_path = os.path.join(temp_dir, file)
            if not os.path.isfile(local_path):
                continue

            ext = file.split(".")[-1]
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            s3_key = f"social_downloads/{unique_name}"

            s3.upload_file(
                local_path,
                settings.AWS_STORAGE_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ACL": "public-read"}
            )

            uploaded_urls.append(
                f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
            )

        return uploaded_urls

    # ----------- CLEANUP TEMP FOLDER -----------
    def clean_files(self, folder_path):
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)




class InstagramPrivateReelDownloadView(APIView):
    def post(self, request):
        url = request.data.get("url")
        ig_username = request.data.get("ig_username") or getattr(settings, "INSTAGRAM_USERNAME", None)
        ig_password = request.data.get("ig_password") or getattr(settings, "INSTAGRAM_PASSWORD", None)

        if not url:
            return Response({"error": "URL is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not ig_username or not ig_password:
            return Response(
                {"error": "Instagram credentials required. Provide ig_username and ig_password in the request or set INSTAGRAM_USERNAME/INSTAGRAM_PASSWORD in settings/.env."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Temporary directory
        temp_dir = "/tmp/instagram_private_downloads"
        os.makedirs(temp_dir, exist_ok=True)

        loader = instaloader.Instaloader(
            dirname_pattern=temp_dir,
            save_metadata=False,
            download_comments=False
        )
        print("!!!!!!!!!!!!!!!!!!************************")

        try:
            # Login for accessing private content
            loader.login(ig_username, ig_password)
            print("Login successful************************")

            # Extract shortcode
            parsed = urlparse(url)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            shortcode = parts[-1] if parts else None
            if not shortcode:
                return Response({"error": "Invalid Instagram URL"}, status=status.HTTP_400_BAD_REQUEST)

            # Download the post
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            loader.download_post(post, target=temp_dir)

            # S3 client
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=getattr(settings, "AWS_S3_REGION_NAME", None)
            )

            uploaded_files = []

            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    local_path = os.path.join(root, file)

                    # File extension
                    ext = file.split(".")[-1]

                    # Generate random 4-digit number
                    random_num = random.randint(1000, 9999)

                    # clean filename
                    new_filename = f"{shortcode}{random_num}.{ext}"

                    # S3 path
                    s3_key = f"instagram_downloads/{shortcode}/{new_filename}"

                    # Upload
                    s3.upload_file(
                        local_path,
                        settings.AWS_STORAGE_BUCKET_NAME,
                        s3_key,
                        ExtraArgs={"ACL": "public-read"}
                    )

                    # Public URL
                    region = getattr(settings, "AWS_S3_REGION_NAME", "ap-south-1")
                    public_url = (
                        f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{region}.amazonaws.com/{s3_key}"
                    )

                    uploaded_files.append(public_url)

            return Response({
                "message": "Private reel downloaded & uploaded to S3 successfully",
                "shortcode": shortcode,
                "s3_files": uploaded_files
            }, status=status.HTTP_200_OK)

        except instaloader.exceptions.BadCredentialsException:
            return Response({"error": "Invalid Instagram credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            return Response({"error": "Two-factor authentication required on the Instagram account"}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            # Clean up
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for n in files:
                    os.remove(os.path.join(root, n))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))


User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = RegisterSerializer(data=request.data)
            if not serializer.is_valid():
                # Flatten first error message
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.save()
            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "status": "success",
                    "message": "User registered successfully.",
                    "data": {
                        "userid": str(user.id),
                        "username": user.name,
                        "email": user.email,
                        "token": {
                            "access_token": str(refresh.access_token),
                            "refresh_token": str(refresh),
                        },
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = LoginSerializer(data=request.data)
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.validated_data["user"]
            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "status": "success",
                    "message": "Login successful.",
                    "data": {
                        "userid": str(user.id),
                        "username": user.name,
                        "email": user.email,
                        "token": {
                            "access_token": str(refresh.access_token),
                            "refresh_token": str(refresh),
                        },
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = ForgotPasswordSerializer(data=request.data)
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            email = serializer.validated_data["email"]
            user = User.objects.get(email__iexact=email)

            # Delete existing OTPs for this user
            OTPVerification.objects.filter(user=user).delete()

            # Generate 6-digit OTP
            otp = f"{random.randint(100000, 999999)}"
            expires_at = timezone.now() + timedelta(minutes=5)

            OTPVerification.objects.create(user=user, otp=otp, expires_at=expires_at)

            subject = "Password Reset OTP"
            message = f"Your OTP for password reset is: {otp}. It expires in 5 minutes."
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [email]

            try:
                send_mail(subject, message, from_email, recipient_list, fail_silently=False)
            except Exception as e:
                return Response(
                    {"status": "error", "message": f"Failed to send email: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            return Response(
                {"status": "success", "message": "OTP sent to your email"},
                status=status.HTTP_200_OK,
            )
        except User.DoesNotExist:
            # Should not usually get here due to serializer validation, but keep clean message
            return Response(
                {"status": "error", "message": "No user found with this email."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            serializer = VerifyOTPSerializer(data=request.data)
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.validated_data["user"]
            otp_obj = serializer.validated_data["otp_obj"]
            new_password = serializer.validated_data["new_password"]

            if otp_obj.is_expired():
                otp_obj.delete()
                return Response(
                    {"status": "error", "message": "OTP has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(new_password)
            user.save()
            otp_obj.delete()

            return Response(
                {"status": "success", "message": "Password reset successfully"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            serializer = LogoutSerializer(data=request.data)
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            refresh_token = serializer.validated_data["refresh_token"]
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                return Response(
                    {
                        "status": "error",
                        "message": f"Failed to blacklist token: {str(e)}",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {"status": "success", "message": "Logged out successfully"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        try:
            user = request.user
            user.delete()
            return Response(
                {"status": "success", "message": "Account deleted successfully"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreateProductView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            serializer = CreateProductSerializer(data=request.data)
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            name = serializer.validated_data["name"]
            description = serializer.validated_data.get("description", "")
            amount = serializer.validated_data["amount"]
            currency = serializer.validated_data.get("currency", "usd")

            stripe_product = stripe.Product.create(name=name, description=description)
            stripe_price = stripe.Price.create(
                product=stripe_product.id,
                unit_amount=int(amount * 100),
                currency=currency,
            )

            product = StripeProduct.objects.create(
                name=name,
                description=description,
                amount=amount,
                currency=currency,
                stripe_product_id=stripe_product.id,
                stripe_price_id=stripe_price.id,
            )

            return Response(
                {
                    "status": "success",
                    "message": "Product created successfully.",
                    "data": {
                        "id": str(product.id),
                        "name": product.name,
                        "amount": str(product.amount),
                        "stripe_product_id": product.stripe_product_id,
                        "stripe_price_id": product.stripe_price_id,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CreatePaymentIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            serializer = CreatePaymentIntentSerializer(data=request.data)
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            product_id = serializer.validated_data["product_id"]
            try:
                product = StripeProduct.objects.get(id=product_id, is_active=True)
            except StripeProduct.DoesNotExist:
                return Response(
                    {"status": "error", "message": "Product not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            payment_intent = stripe.PaymentIntent.create(
                amount=int(product.amount * 100),
                currency=product.currency,
                metadata={"user_id": str(request.user.id), "product_id": str(product.id)},
            )

            Payment.objects.create(
                user=request.user,
                product=product,
                stripe_payment_intent_id=payment_intent.id,
                amount=product.amount,
                currency=product.currency,
                status="pending",
                metadata=payment_intent.get("metadata", {}),
            )

            return Response(
                {
                    "status": "success",
                    "message": "Payment intent created successfully.",
                    "data": {
                        "client_secret": payment_intent.client_secret,
                        "payment_intent_id": payment_intent.id,
                        "amount": str(product.amount),
                        "currency": product.currency,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            payload = request.body
            sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
                )
            except ValueError:
                return Response(
                    {"status": "error", "message": "Invalid payload"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except stripe.error.SignatureVerificationError:
                return Response(
                    {"status": "error", "message": "Invalid signature"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            event_type = event.get("type")
            payment_intent_id = event.get("data", {}).get("object", {}).get("id")

            if event_type in [
                "payment_intent.succeeded",
                "payment_intent.payment_failed",
                "payment_intent.canceled",
            ] and payment_intent_id:
                try:
                    payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
                    if event_type == "payment_intent.succeeded":
                        payment.status = "succeeded"
                    elif event_type == "payment_intent.payment_failed":
                        payment.status = "failed"
                    elif event_type == "payment_intent.canceled":
                        payment.status = "canceled"
                    payment.save()
                except Payment.DoesNotExist:
                    print(f"Payment not found for payment_intent_id: {payment_intent_id}")

            return Response(
                {"status": "success", "message": "ok"},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PaymentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_intent_id):
        try:
            serializer = PaymentStatusSerializer(
                data={"stripe_payment_intent_id": payment_intent_id}
            )
            if not serializer.is_valid():
                first_error = next(iter(serializer.errors.values()))[0]
                return Response(
                    {"status": "error", "message": str(first_error)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                payment = Payment.objects.get(
                    stripe_payment_intent_id=serializer.validated_data["stripe_payment_intent_id"],
                    user=request.user,
                )
            except Payment.DoesNotExist:
                return Response(
                    {"status": "error", "message": "Payment not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                {
                    "status": "success",
                    "message": "Payment status fetched successfully.",
                    "data": {
                        "payment_intent_id": payment.stripe_payment_intent_id,
                        "status": payment.status,
                        "amount": str(payment.amount),
                        "currency": payment.currency,
                        "product_name": payment.product.name if payment.product else None,
                        "created_at": payment.created_at,
                    },
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )