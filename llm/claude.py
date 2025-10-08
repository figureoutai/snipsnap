import json
import boto3

from base_llm import LLM
from botocore.config import Config
from utils.logger import app_logger as logger
from utils.helpers import encode_image_to_base64, extract_json, retry_with_backoff

class Claude(LLM):
    def __init__(self):
        super().__init__()
        self.llm = boto3.client("bedrock-runtime", region_name="us-east-1", config=Config(read_timeout=300))
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"


    def load_model(self, *args, **kwargs):
        return Claude()
    
    def generate(self, prompt):
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": prompt},
                ]
            }
        ]
        body = {
            "messages": messages,
            "max_tokens": 1500,
            "temperature": 0.1,
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
        return content_text
    

    def get_captions(self, img_path):
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "CAPTION_PROMPT"},
                    {
                        "type": "image", 
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": encode_image_to_base64(img_path)}
                    }
                ]
            }
        ]
        body = {
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.1,
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
        return content_text
    
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def calculate_relevance_score(self, images_metadata):
        images_metadata = json.loads(images_metadata)
        content = [{"type": "text", "text": json.dumps(frame)} for frame in images_metadata["frames"]]
        content.append({
            "type": "text", 
            "text": json.dumps({"central_img_idx": images_metadata["central_img_idx"]}),
            "cache_control": {"type": "ephemeral"}
        })
        # content = [{"type": "text", "text": "Hello World"}]

        messages = [
            {
                "role": "user", 
                "content": content
            }
        ]
        body = {
            "messages": messages,
            "system": [{"type": "text", "text": "RELEVANCE_SCORER_PROMPT"}],
            "max_tokens": 1500,
            "temperature": 0,
            "anthropic_version": "bedrock-2023-05-31"
        }
        logger.info(json.dumps(body))

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
        return extract_json(content_text)
    
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def extract_highlights(self, metadata):
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "HIGHLIGHTS_PROMPT"},
                    {"type": "text", "text": metadata}
                ]
            }
        ]
        body = {
            "messages": messages,
            "max_tokens": 4000,
            "temperature": 0.1,
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
        return extract_json(content_text)
