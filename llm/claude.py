import json
from typing import List
from botocore.config import Config
from aiobotocore.session import get_session

from .base_llm import LLM
from utils.logger import app_logger as logger
from utils.helpers import extract_json, retry_with_backoff, EMPTY_STRING


class Claude(LLM):
    def __init__(self):
        super().__init__()
        self.region = "us-east-1"
        self.model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"
        self.config = Config(read_timeout=300)
        self.session = get_session()

    @retry_with_backoff(retries=5, backoff_in_seconds=5)
    async def invoke(self, prompt: str, response_type: str, queries: List[str] = [], images: List[str] = [], max_tokens: int = 300,):
        content = [
            *[{"type": "text", "text": query} for query in queries if query and query != EMPTY_STRING],
            *[
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img,
                    },
                }
                for img in images
            ],
        ]

        body = {
            "messages": [{"role": "user", "content": content}],
            "system": [{"type": "text", "text": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "anthropic_version": "bedrock-2023-05-31",
        }

        async with self.session.create_client("bedrock-runtime", region_name=self.region, config=self.config) as client:
            logger.info(f"[Claude] Invoking {self.model_id}")
            response = await client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )

            async with response["body"] as stream:
                body_bytes = await stream.read()

        output = json.loads(body_bytes)
        logger.info(f"[Claude] Output: {output}")

        content_text = output["content"][0]["text"]
        return extract_json(content_text) if response_type == "json" else content_text
