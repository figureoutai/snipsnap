import json
import boto3

from base_llm import LLM
from botocore.config import Config
from utils.logger import app_logger as logger
from utils.helpers import encode_image_to_base64, extract_json, retry_with_backoff

class NovaPremier(LLM):
    def __init__(self):
        super().__init__()
        self.llm = boto3.client("bedrock-runtime", region_name="us-east-1", config=Config(read_timeout=300))

    def get_image_content(self, img_path):
        return {
            "image": {
                "format": "jpg",
                "source": {
                    "bytes": encode_image_to_base64(img_path)
                }
            }
        }
    
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def get_captions(self, img_path):
        system_list = [
            {
                "text": "CAPTION_PROMPT"
            }
        ]

        message_list = [
            {
                "role": "user",
                "content": [
                    self.get_image_content(img_path)
                ]
            }
        ]

        # Configure the inference parameters.
        inf_params = {"maxTokens": self.max_tokens, "topP": 0.9, "temperature": 0.01}

        native_request = {
            "schemaVersion": "messages-v1",
            "messages": message_list,
            "system": system_list,
            "inferenceConfig": inf_params,
        }

        # Invoke the model and extract the response body.
        response = self.llm.invoke_model(modelId="us.amazon.nova-premier-v1:0", body=json.dumps(native_request))
        model_response = json.loads(response["body"].read())
        content_text = model_response["output"]["message"]["content"][0]["text"]

        return content_text
    
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def calculate_relevance_score(self, images_metadata):
        system_list = [
            {
                "text": "RELEVANCE_SCORER_PROMPT"
            }
        ]

        images_metadata = json.loads(images_metadata)
        content = [{"text": json.dumps(frame)} for frame in images_metadata["frames"]]
        content.append({
            "text": json.dumps({"central_img_idx": images_metadata["central_img_idx"]}),
            "cachePoint": {"type": "default"}
        })

        messages = [
            {
                "role": "user",
                "content": content
            }
        ]

        # Configure the inference parameters.
        inf_params = {"maxTokens": 500, "topP": 0.9, "temperature": 0}

        native_request = {
            "schemaVersion": "messages-v1",
            "messages": messages,
            "system": system_list,
            "inferenceConfig": inf_params,
        }

        # Invoke the model and extract the response body.
        response = self.llm.invoke_model(modelId="us.amazon.nova-premier-v1:0", body=json.dumps(native_request))
        model_response = json.loads(response["body"].read())
        content_text = model_response["output"]["message"]["content"][0]["text"]
        logger.info(f"Printing response from LLM: {model_response}" )
        logger.info(f"Model Output: {model_response["output"]}")
        logger.info(f"Model Output Message: {model_response["output"]["message"]}")
        logger.info(f"Model Output Message Content: {model_response["output"]["message"]["content"]}")
        logger.info(f"Model Output Message Content 0: {model_response["output"]["message"]["content"][0]}")

        return extract_json(content_text)

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def extract_highlights(self, metadata):
        system_list = [
            {
                "text": "HIGHLIGHTS_PROMPT"
            }
        ]

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": metadata
                    }
                ]
            }
        ]

        # Configure the inference parameters.
        inf_params = {"maxTokens": 3000, "topP": 0.9, "temperature": 0.01}

        native_request = {
            "schemaVersion": "messages-v1",
            "messages": messages,
            "system": system_list,
            "inferenceConfig": inf_params,
        }

        # Invoke the model and extract the response body.
        response = self.llm.invoke_model(modelId="us.amazon.nova-premier-v1:0", body=json.dumps(native_request))
        model_response = json.loads(response["body"].read())
        content_text = model_response["output"]["message"]["content"][0]["text"]
        return extract_json(content_text) 


class LLava(LLM):
    def __init__(self):
        super().__init__()

    def get_captions(self, img_path):
        return super().get_captions_from_llm(img_path)
