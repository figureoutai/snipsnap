import os
import json
import asyncio
import logging

from .handler import get_secret
from .aurora_service import AuroraService

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SECRET_NAME = os.environ["SECRET_NAME"]
DB_URL = os.environ["DB_URL"]
DB_NAME = os.environ["DB_NAME"]

def get_highlights(event, context):
    try:
        query_params = event.get('queryStringParameters')
        if "stream_id" not in query_params:
            raise KeyError("stream_id not found in Query Parameters.")
        stream_id = query_params["stream_id"]

        logger.info("connecting to db")

        secrets = get_secret(SECRET_NAME)
        db_service = AuroraService(
            host=DB_URL,
            user=secrets["username"],
            password=secrets["password"],
            database=DB_NAME,
        )
        asyncio.run(db_service.initialize())

        logger.info("successfully connected to db.")

        result = asyncio.run(db_service.get_highlights_by_stream(stream_id))

        return  {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result),
        }

    except Exception as e:
        logger.exception("video_receiver failed: %s", e)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"ok": False, "error": str(e)}),
        }