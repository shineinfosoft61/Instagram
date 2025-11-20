import os
import random
import boto3
from urllib.parse import urlparse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import instaloader
from django.conf import settings

class InstagramDownloadView(APIView):
    def post(self, request):
        url = request.data.get("url")
        if not url:
            return Response({"error": "URL is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Temporary directory
        temp_dir = "/tmp/instagram_downloads"
        os.makedirs(temp_dir, exist_ok=True)

        loader = instaloader.Instaloader(
            dirname_pattern=temp_dir,
            save_metadata=False,
            download_comments=False
        )

        try:
            # Extract shortcode
            parsed = urlparse(url)
            shortcode = parsed.path.strip("/").split("/")[-1]

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

                    # NEW clean filename
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
                "message": "Downloaded & uploaded to S3 successfully",
                "shortcode": shortcode,
                "s3_files": uploaded_files
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        finally:
            # Clean up
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for n in files:
                    os.remove(os.path.join(root, n))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))
