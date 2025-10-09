import json
import boto3

from typing import List
from .base_llm import LLM
from botocore.config import Config
from utils.logger import app_logger as logger
from utils.helpers import encode_image_to_base64, extract_json, retry_with_backoff

class Claude(LLM):
    def __init__(self):
        super().__init__()
        self.llm = boto3.client("bedrock-runtime", region_name="us-east-1", config=Config(read_timeout=300))
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def invoke(self, prompt: str, response_type: str, query: str="", images: List[str]=[], max_tokens=300):
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": query},
                    *[
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": img}
                        } for img in images
                    ]
                ]
            }
        ]
        body = {
            "messages": messages,
            "system": [{"type": "text", "text": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "anthropic_version": "bedrock-2023-05-31"
        }

        response = self.llm.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json"
        )

        # Parse response
        output = json.loads(response["body"].read())
        content_text = output["content"][0]["text"]
        logger.info(f"Output: {output}")
        if response_type == "json":
            return extract_json(content_text)
        return content_text
