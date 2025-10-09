import json
import os
import boto3

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

        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody= message if isinstance(message, str) else json.dumps(message),
        )

        resp = {"ok": True, "queued": message}
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(resp),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": False, "error": str(e)}),
        }