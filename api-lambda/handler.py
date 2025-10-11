import json
import logging
import os
import asyncio

import boto3
from aurora_service import AuroraService

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]
SECRET_NAME = os.environ["SECRET_NAME"]
DB_URL = os.environ["DB_URL"]


print("version 2")

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

        message = body.get("message", "hello from lambda 👋")
        
        logger.info("Received message: %s", message)
        logger.info("connecting to db")

        secrets = get_secret(SECRET_NAME)

        db_service = AuroraService(
            host=DB_URL,
            user=secrets["username"],
            password=secrets["password"],
            database="strangedb",
        )

        asyncio.run(db_service.initialize())

        logger.info("successfully connected to db")

        try:
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=message if isinstance(message, str) else json.dumps(message),
            )
        except Exception as sqs_error:
            logger.exception("Failed to post message to SQS: %s", sqs_error)
            raise

        resp = {"ok": True, "queued": message}
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(resp),
        }

    except Exception as e:
        logger.exception("video_receiver failed: %s", e)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": False, "error": str(e)}),
        }
