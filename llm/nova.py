import json
import boto3

from typing import List
from base_llm import LLM
from botocore.config import Config
from utils.logger import app_logger as logger
from utils.helpers import encode_image_to_base64, extract_json, retry_with_backoff

class NovaPremier(LLM):
    def __init__(self):
        super().__init__()
        self.llm = boto3.client("bedrock-runtime", region_name="us-east-1", config=Config(read_timeout=300))

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def invoke(self, prompt: str, response_type: str, query: str="", images: List[str]=[], max_tokens=300):
        messages = [
            {
                "role": "user", 
                "content": [
                    {"text": query},
                    {
                        "image": {
                            "format": "jpg", "source": {"bytes": img}
                        }
                    } for img in images
                ]
            }
        ]

        # Configure the inference parameters.
        inf_params = {"maxTokens": max_tokens, "topP": 0.9, "temperature": 0.01}

        native_request = {
            "schemaVersion": "messages-v1",
            "messages": messages,
            "system": [{"text": prompt}],
            "inferenceConfig": inf_params,
        }

        # Invoke the model and extract the response body.
        response = self.llm.invoke_model(modelId="us.amazon.nova-premier-v1:0", body=json.dumps(native_request))
        model_response = json.loads(response["body"].read())
        content_text = model_response["output"]["message"]["content"][0]["text"]

        return extract_json(content_text) if response_type == "json" else content_text
    