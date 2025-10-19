import boto3
import os

def upload_directory(local_directory, bucket_name, s3_prefix=""):
    """
    Recursively uploads a directory to an S3 bucket.

    Args:
        local_directory (str): The local folder to upload.
        bucket_name (str): S3 bucket name.
        s3_prefix (str): Optional S3 path prefix.
    """

    s3_client = boto3.client("s3")

    for root, _, files in os.walk(local_directory):
        for file in sorted(files):
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_directory)
            s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")

            print(f"Uploading {local_path} → s3://{bucket_name}/{s3_key}")
            s3_client.upload_file(local_path, bucket_name, s3_key)

# Example usage
upload_directory(
    local_directory="./data/test_videos/agadmator-chess",
    bucket_name="highlight-clipping-service-main-975049899047",
    s3_prefix="streams/28bf1156/video"
)
