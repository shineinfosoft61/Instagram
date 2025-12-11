import os
import random
import re
import boto3
from urllib.parse import urlparse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import instaloader
from django.conf import settings

import yt_dlp
import instaloader
import os, random, boto3
from urllib.parse import urlparse


class Ping(APIView):
    def post(self, request):
        return Response({"success": "health is ok"}, status=200)

class InstagramDownloadView(APIView):
    def post(self, request):
        url = request.data.get("url")
        if not url:
            return Response({"error": "URL is required"}, status=400)

        temp_dir = "/tmp/social_downloads"
        os.makedirs(temp_dir, exist_ok=True)

        uploaded_files = []

        try:
            # ---------- PLATFORM DETECTOR ----------
            if "instagram.com" in url:
                uploaded_files = self.download_instagram(url, temp_dir)

            elif "whatsapp.com" in url or "wa.me" in url:
                uploaded_files = self.download_with_ytdlp(url, temp_dir)

            elif "facebook.com" in url or "fb.watch" in url:
                uploaded_files = self.download_with_ytdlp(url, temp_dir)

            else:
                return Response({"error": "Unsupported URL platform"}, status=400)

            # Upload to s3
            s3_urls = self.upload_to_s3(uploaded_files)

            return Response({
                "message": "Downloaded Successfully",
                "downloads": s3_urls
            }, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

        finally:
            self.clean_files(temp_dir)

    # --------------- INSTAGRAM --------------------
    def download_instagram(self, url, temp_dir):
        parsed = urlparse(url)
        shortcode = parsed.path.strip("/").split("/")[-1]

        loader = instaloader.Instaloader(dirname_pattern=temp_dir, save_metadata=False)
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target=temp_dir)

        return os.listdir(temp_dir)

    # -------- FACEBOOK + WHATSAPP (yt-dlp) --------
    def download_with_ytdlp(self, url, temp_dir):
        outtmpl = os.path.join(temp_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": "best",
            "restrictfilenames": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return os.listdir(temp_dir)

    # --------------- S3 Upload --------------------
    def upload_to_s3(self, files):
        s3 = boto3.client("s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)

        result_urls = []
        for file in files:
            local = f"/tmp/social_downloads/{file}"
            ext = file.split(".")[-1]
            new = f"{random.randint(1111,9999)}.{ext}"
            s3_key = f"social_downloads/{new}"

            s3.upload_file(local, settings.AWS_STORAGE_BUCKET_NAME, s3_key, ExtraArgs={"ACL": "public-read"})
            result_urls.append(f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{s3_key}")

        return result_urls

    def clean_files(self, path):
        for root,dirs,files in os.walk(path):
            for f in files: os.remove(os.path.join(root,f))



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

