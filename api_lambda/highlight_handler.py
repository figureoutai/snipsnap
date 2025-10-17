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
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")

# Global pool (shared across invocations)
db_service: AuroraService | None = None
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

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

async def get_list_of_streams(page: int = 1, limit: int = 20, status: str = None):
    logger.info("connecting to db")
    service = await init_db()
    logger.info("successfully connected to db")
    return await service.get_available_streams(
        page=page,
        limit=limit,
        status=status
    )

async def get_highlights_by_stream(stream_id: str):
    logger.info("connecting to db")
    service = await init_db()
    logger.info("successfully connected to db")
    return await service.get_highlights_by_stream(stream_id)

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

def get_streams(event, context):
    try:
        # Get query parameters with defaults
        query_params = event.get('queryStringParameters', {}) or {}
        page = int(query_params.get('page', 1))
        limit = int(query_params.get('limit', 20))
        status = query_params.get('status')

        # Get streams with pagination
        result = loop.run_until_complete(get_list_of_streams(
            page=page,
            limit=limit,
            status=status
        ))

        return {
            "statusCode": 200,
            "headers": _cors_headers(event),
            "body": json.dumps(result),
        }

    except Exception as e:
        logger.exception("get_streams failed: %s", e)
        return {
            "statusCode": 500,
            "headers": _cors_headers(event),
            "body": json.dumps({"ok": False, "error": str(e)}),
        }

def get_highlights(event, context):
    try:
        query_params = event.get('queryStringParameters')
        if "stream_id" not in query_params:
            raise KeyError("stream_id not found in Query Parameters.")
        stream_id = query_params["stream_id"]

        result = loop.run_until_complete(get_highlights_by_stream(stream_id))

        return  {
            "statusCode": 200,
            "headers": _cors_headers(event),
            "body": json.dumps(result),
        }

    except Exception as e:
        logger.exception("video_receiver failed: %s", e)
        return {
            "statusCode": 500,
            "headers": _cors_headers(event),
            "body": json.dumps({"ok": False, "error": str(e)}),
        }
