import json
import logging
import os
import asyncio

import boto3
from aurora_service import AuroraService

logger = logging.getLogger(__name__)

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]

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

        db_service = AuroraService(
            host="database-1.cluster-ckdseak4qyg6.us-east-1.rds.amazonaws.com",
            user="<username>",
            password="<password>",
            database="strangedb",
        )

        asyncio.run(db_service.initialize())

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
