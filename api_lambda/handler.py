import os
import json
import time
import uuid
import boto3
import asyncio
import logging
import requests


from .aurora_service import AuroraService


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global pool (shared across invocations)
db_service: AuroraService | None = None
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


batch = boto3.client("batch")
JOB_QUEUE = os.environ["BATCH_JOB_QUEUE"]
JOB_DEFINITION = os.environ["BATCH_JOB_DEFINITION"]
SECRET_NAME = os.environ["SECRET_NAME"]
DB_URL = os.environ["DB_URL"]
DB_NAME = os.environ["DB_NAME"]
STREAM_METADATA_TABLE = os.environ["STREAM_METADATA_TABLE"]
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")

print("version 2")

VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/x-flv",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "video/MP2T",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
}

def is_video_url(url: str, timeout: int = 8) -> bool:
    """
    Check if the given URL is accessible and serves actual video content.
    """
    try:
        # Use HEAD first — lighter request
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        content_type = response.headers.get("Content-Type", "").lower()

        # If no content-type or it's generic, fallback to GET (some servers block HEAD)
        if not content_type or "text/html" in content_type:
            response = requests.get(url, stream=True, allow_redirects=True, timeout=timeout)
            content_type = response.headers.get("Content-Type", "").lower()

        # ✅ Confirm it's accessible and serves video content
        if response.status_code == 200 and any(ct in content_type for ct in VIDEO_CONTENT_TYPES):
            return True

        return False

    except requests.RequestException:
        return False


def _cors_headers(event):
    
    origin = None
    if 'headers' in event:
        headers = event['headers']
        origin = headers.get('origin') or headers.get('Origin')
    
    selected_origin = FRONTEND_ORIGIN
    if origin and (origin in ALLOWED_ORIGINS):
        selected_origin = origin
    
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": selected_origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def get_secret(secret_name: str, region_name: str = "us-east-1"):
    # Create a Secrets Manager client
    client = boto3.client("secretsmanager", region_name=region_name)

    try:
        # Get the secret value
        response = client.get_secret_value(SecretId=secret_name)

        # The secret can be either a string or binary
        if "SecretString" in response:
            secret = response["SecretString"]
            return json.loads(secret)  # Parse JSON string if applicable
        else:
            # Decode binary secret
            secret = response["SecretBinary"]
            return secret.decode("utf-8")

    except Exception as e:
        logger.error(f"❌ The requested secret {secret_name} was not found")

async def init_db():
    global db_service
    if db_service is None:
        secrets = get_secret(SECRET_NAME)
        db_service = AuroraService(
            host=DB_URL,
            user=secrets["username"],
            password=secrets["password"],
            database=DB_NAME,
        )
        await db_service.initialize()
    return db_service

async def insert_dict(table_name: str, data: dict):
    logger.info("connecting to db")
    service = await init_db()
    logger.info("successfully connected to db")
    return await service.insert_dict(table_name, data)


def video_receiver(event, context):
    """
    Expects:
      - Direct invoke: {"message": "hello world"}
      - HTTP POST (via API Gateway HTTP API): JSON body {"message": "hello world"}
    """
    try:
        # Handle both direct invocation and HTTP API body
        body = event.get("body", event) or {}
        if isinstance(body, str):
            body = json.loads(body or "{}")

        stream_url = body.get("stream_url", None)

        if not stream_url:
            raise KeyError("stream_url is required to start the pipeline.")
        
        if not is_video_url(stream_url):
            raise ValueError("stream_url is not reachable or the content is not in supported video formats")

        logger.info("Received stream url: %s", stream_url)

        stream_id = uuid.uuid4().hex[:8]
        job_name = f"video-job-{int(time.time())}-{stream_id}"
        payload = json.dumps({
            "stream_url": stream_url,
            "stream_id": stream_id
        })

        stream_metadata = {
            "stream_url": stream_url,
            "stream_id": stream_id,
            "status": "SUBMITTED"
        }

        loop.run_until_complete(insert_dict(STREAM_METADATA_TABLE, stream_metadata))

        try:
            submission = batch.submit_job(
                jobName=job_name,
                jobQueue=JOB_QUEUE,
                jobDefinition=JOB_DEFINITION,
                containerOverrides={
                    "environment": [
                        {"name": "JOB_MESSAGE", "value": payload},
                    ]
                },
            )
        except Exception as batch_error:
            logger.exception("Failed to submit AWS Batch job: %s", batch_error)
            raise

        resp = {
            "ok": True,
            "jobName": submission.get("jobName", job_name),
            "jobId": submission.get("jobId"),
            "payload": payload,
        }
        return {
            "statusCode": 200,
            "headers": _cors_headers(event),
            "body": json.dumps(resp),
        }

    except (KeyError, ValueError) as e:
        # Client error: missing or invalid stream_url
        message = e.args[0] if getattr(e, "args", None) else str(e)
        logger.warning("Bad request: %s", message)
        return {
            "statusCode": 400,
            "headers": _cors_headers(event),
            "body": json.dumps({"ok": False, "error": message}),
        }
    except Exception as e:
        logger.exception("video_receiver failed: %s", e)
        return {
            "statusCode": 500,
            "headers": _cors_headers(event),
            "body": json.dumps({"ok": False, "error": str(e)}),
        }
