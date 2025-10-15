import aioboto3
import asyncio
import os
from typing import Optional, Dict, Any
from pathlib import Path
import mimetypes
import aiofiles
from pathlib import Path
from datetime import datetime
from utils.logger import app_logger as logger


class S3Service:

    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "us-east-1",
        audio_prefix: str = "audio/",
        image_prefix: str = "images/",
    ):
        """
        Initialize the S3 service.

        Args:
            bucket_name: Name of the S3 bucket
            aws_access_key_id: AWS access key (uses env var if None)
            aws_secret_access_key: AWS secret key (uses env var if None)
            region_name: AWS region
            audio_prefix: Prefix for audio files in S3
            image_prefix: Prefix for image files in S3
        """
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.audio_prefix = audio_prefix
        self.image_prefix = image_prefix

        # Use provided credentials or fall back to environment variables
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv(
            "AWS_SECRET_ACCESS_KEY"
        )

        self.session = aioboto3.Session(
            # aws_access_key_id=self.aws_access_key_id,
            # aws_secret_access_key=self.aws_secret_access_key,
            # region_name=self.region_name,
        )

        # Track pending uploads
        self.pending_uploads = set()

        logger.info(f"AsyncS3Service initialized for bucket: {bucket_name}")

    def _get_content_type(self, filename: str) -> str:
        """Determine content type from filename."""
        content_type, _ = mimetypes.guess_type(filename)
        if content_type:
            return content_type

        # Default content types for common audio/image formats
        ext = Path(filename).suffix.lower()
        defaults = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".flac": "audio/flac",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return defaults.get(ext, "application/octet-stream")

    def _generate_s3_key(
        self, stream_id: str, filename: str, prefix: str, add_timestamp: bool = True
    ) -> str:
        """Generate S3 key with optional timestamp."""
        if add_timestamp:
            name = Path(filename).stem
            ext = Path(filename).suffix
            # filename = f"{name}_{timestamp}{ext}"
            filename = f"{name}{ext}"

        return f"{stream_id}/{prefix}{filename}"

    async def upload_audio(
        self,
        stream_id,
        file_path: Optional[str] = None,
        file_data: Optional[bytes] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        add_timestamp: bool = True,
        storage_class: str = "STANDARD",
    ) -> Dict[str, Any]:
        """
        Upload an audio clip to S3.

        Args:
            file_path: Path to audio file on disk
            file_data: Raw audio bytes (alternative to file_path)
            filename: Name for the file in S3 (required if using file_data)
            metadata: Additional metadata to store with the file
            add_timestamp: Add timestamp to filename
            storage_class: S3 storage class (STANDARD, INTELLIGENT_TIERING, etc.)

        Returns:
            Dictionary with upload details (key, url, etag)
        """
        if file_path:
            filename = filename or os.path.basename(file_path)
            async with aiofiles.open(file_path, "rb") as f:
                file_data = await f.read()
        elif file_data is None:
            raise ValueError("Either file_path or file_data must be provided")

        if not filename:
            raise ValueError("filename must be provided when using file_data")

        s3_key = self._generate_s3_key(stream_id, filename, self.audio_prefix, add_timestamp)
        content_type = self._get_content_type(filename)

        extra_args = {"ContentType": content_type, "StorageClass": storage_class}

        if metadata:
            extra_args["Metadata"] = metadata

        async with self.session.client("s3") as s3:
            response = await s3.put_object(
                Bucket=self.bucket_name, Key=s3_key, Body=file_data, **extra_args
            )

        result = {
            "key": s3_key,
            "bucket": self.bucket_name,
            "url": f"s3://{self.bucket_name}/{s3_key}",
            "https_url": f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{s3_key}",
            "etag": response.get("ETag", "").strip('"'),
            "content_type": content_type,
            "size": len(file_data),
        }

        logger.info(f"Uploaded audio: {s3_key}")
        return result

    async def upload_image(
        self,
        stream_id,
        file_path: Optional[str] = None,
        file_data: Optional[bytes] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        add_timestamp: bool = True,
        storage_class: str = "STANDARD",
    ) -> Dict[str, Any]:
        """
        Upload an image to S3.

        Args:
            file_path: Path to image file on disk
            file_data: Raw image bytes (alternative to file_path)
            filename: Name for the file in S3 (required if using file_data)
            metadata: Additional metadata to store with the file
            add_timestamp: Add timestamp to filename
            storage_class: S3 storage class

        Returns:
            Dictionary with upload details (key, url, etag)
        """
        if file_path:
            filename = filename or os.path.basename(file_path)
            async with aiofiles.open(file_path, "rb") as f:
                file_data = await f.read()
        elif file_data is None:
            raise ValueError("Either file_path or file_data must be provided")

        if not filename:
            raise ValueError("filename must be provided when using file_data")

        s3_key = self._generate_s3_key(stream_id, filename, self.image_prefix, add_timestamp)
        content_type = self._get_content_type(filename)

        extra_args = {"ContentType": content_type, "StorageClass": storage_class}

        if metadata:
            extra_args["Metadata"] = metadata

        async with self.session.client("s3") as s3:
            response = await s3.put_object(
                Bucket=self.bucket_name, Key=s3_key, Body=file_data, **extra_args
            )

        result = {
            "key": s3_key,
            "bucket": self.bucket_name,
            "url": f"s3://{self.bucket_name}/{s3_key}",
            "https_url": f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{s3_key}",
            "etag": response.get("ETag", "").strip('"'),
            "content_type": content_type,
            "size": len(file_data),
        }

        logger.info(f"Uploaded image: {s3_key}")
        return result

    def _handle_upload_result(self, task: asyncio.Task):
        """Callback to handle upload task completion."""
        try:
            result = task.result()
            logger.debug(f"Upload completed: {result['key']}")
        except Exception as e:
            logger.error(f"Upload failed: {e}")

    def upload_audio_nowait(
        self,
        stream_id: str,
        file_path: Optional[str] = None,
        file_data: Optional[bytes] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        add_timestamp: bool = True,
    ) -> asyncio.Task:
        """
        Fire-and-forget audio upload (non-blocking).

        Returns:
            asyncio.Task that can be awaited later if needed
        """
        task = asyncio.create_task(
            self.upload_audio(stream_id, file_path, file_data, filename, metadata, add_timestamp)
        )
        self.pending_uploads.add(task)
        task.add_done_callback(lambda t: self.pending_uploads.discard(t))
        task.add_done_callback(self._handle_upload_result)
        return task

    def upload_image_nowait(
        self,
        stream_id: str,
        file_path: Optional[str] = None,
        file_data: Optional[bytes] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        add_timestamp: bool = True,
    ) -> asyncio.Task:
        """
        Fire-and-forget image upload (non-blocking).

        Returns:
            asyncio.Task that can be awaited later if needed
        """
        task = asyncio.create_task(
            self.upload_image(stream_id, file_path, file_data, filename, metadata, add_timestamp)
        )
        self.pending_uploads.add(task)
        task.add_done_callback(lambda t: self.pending_uploads.discard(t))
        task.add_done_callback(self._handle_upload_result)
        return task

    async def download_audio(
        self, s3_key: str, local_path: Optional[str] = None
    ) -> bytes:
        """
        Download an audio file from S3.

        Args:
            s3_key: S3 key of the audio file
            local_path: Optional path to save the file locally

        Returns:
            Audio file bytes
        """
        async with self.session.client("s3") as s3:
            response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            async with response["Body"] as stream:
                file_data = await stream.read()

        if local_path:
            async with aiofiles.open(local_path, "wb") as f:
                await f.write(file_data)
            logger.info(f"Downloaded audio to: {local_path}")

        return file_data

    async def download_image(
        self, s3_key: str, local_path: Optional[str] = None
    ) -> bytes:
        """
        Download an image from S3.

        Args:
            s3_key: S3 key of the image
            local_path: Optional path to save the file locally

        Returns:
            Image file bytes
        """
        async with self.session.client("s3") as s3:
            response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            async with response["Body"] as stream:
                file_data = await stream.read()

        if local_path:
            async with aiofiles.open(local_path, "wb") as f:
                await f.write(file_data)
            logger.info(f"Downloaded image to: {local_path}")

        return file_data

    async def get_presigned_url(
        self, s3_key: str, expiration: int = 3600, http_method: str = "get_object"
    ) -> str:
        """
        Generate a presigned URL for accessing a file.

        Args:
            s3_key: S3 key of the file
            expiration: URL expiration time in seconds (default: 1 hour)
            http_method: HTTP method (get_object, put_object)

        Returns:
            Presigned URL
        """
        async with self.session.client("s3") as s3:
            url = await s3.generate_presigned_url(
                http_method,
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )

        return url

    async def wait_for_pending_uploads(self, timeout: Optional[float] = None):
        """
        Wait for all pending uploads to complete.

        Args:
            timeout: Maximum time to wait in seconds
        """
        if self.pending_uploads:
            logger.info(f"Waiting for {len(self.pending_uploads)} pending uploads...")
            await asyncio.wait(self.pending_uploads, timeout=timeout)
            logger.info("All pending uploads completed")
