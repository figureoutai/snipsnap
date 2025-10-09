import boto3
import json

from botocore.exceptions import ClientError
from utils.logger import app_logger as logger


class SQSService:
    def __init__(self, queue_url: str, region_name: str = "us-east-1"):
        """
        Initialize the SQS service client.
        """
        self.sqs = boto3.client("sqs", region_name=region_name)
        self.queue_url = queue_url

    def receive_message(self, max_messages: int = 1, wait_time: int = 10):
        """
        Receive messages from the SQS queue.
        """
        try:
            response = self.sqs.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time,
                VisibilityTimeout=30  # seconds to hide the message from other consumers
            )

            messages = response.get("Messages", [])
            if not messages:
                logger.info("No messages available.")
                return []

            for msg in messages:
                logger.info(f"Received message: {msg['MessageId']}")
                logger.debug(f"Message body: {msg['Body']}")
            return messages

        except ClientError as e:
            logger.error(f"Error receiving message: {e}")
            return []

    def delete_message(self, receipt_handle: str):
        """
        Delete a message from the queue after successful processing.
        """
        try:
            self.sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
            logger.info("Message deleted successfully.")
        except ClientError as e:
            logger.error(f"Error deleting message: {e}")


if __name__ == "__main__":
    # Example usage
    QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/my-queue"

    sqs_service = SQSService(queue_url=QUEUE_URL)

    messages = sqs_service.receive_message()

    for msg in messages:
        body = json.loads(msg["Body"])  # if you published JSON data
        logger.info(f"Processing message: {body}")

        # Once processed, delete the message
        sqs_service.delete_message(msg["ReceiptHandle"])
