import re
import cv2
import json
import time
import boto3
import base64
import random
import asyncio
import requests
import functools
import numpy as np

from .logger import app_logger as logger

EMPTY_STRING = "!EMPTY!"
ERROR_STRING = "!ERROR!"

VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/x-flv",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "video/MP2T",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
}

def get_audio_filename(idx: int):
    return f"audio_{idx:06d}.wav"

def get_video_frame_filename(idx: int):
    return f"frame_{idx:09d}.jpg"

async def run_sync_func(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)


def save_audio(audio_frames, sr, layout, output_path="output.wav"):
    import av
    # create output container
    output = av.open(output_path, mode='w')
    stream = output.add_stream('pcm_s16le', rate=sr)  # 16-bit PCM
    print(audio_frames.shape, sr)

    frame = av.AudioFrame.from_ndarray(audio_frames, format='s16', layout=layout)
    frame.sample_rate = sr

    for packet in stream.encode(frame):
        output.mux(packet)

    # flush encoder
    for packet in stream.encode(None):
        output.mux(packet)

    output.close()
    print(f"Audio saved to {output_path}")

def encode_image_to_base64(img_path):
    with open(img_path, "rb") as img:
        return base64.b64encode(img.read()).decode("utf-8")
    
def numpy_to_base64(img: np.ndarray, format: str = 'jpg') -> str:
    success, buffer = cv2.imencode(f'.{format}', img)
    if not success:
        raise ValueError("Could not encode image.")
    return base64.b64encode(buffer).decode('utf-8')


def extract_json(text: str):
    """
    Extracts the first valid JSON object or array from a string.
    Handles:
      - ```json ... ``` fences
      - Single object {...}
      - List of objects [...]
    Returns: parsed Python object (dict or list)
    """
    if not text:
        return {}

    try:
        # Remove markdown fences if present
        cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.DOTALL).strip()

        # Find JSON block: can start with { or [
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON object or array found")

        json_str = match.group(0).strip()

        return json.loads(json_str)

    except Exception as e:
        print("Error parsing JSON:", e, f"\nText:\n{text}")
        Exception(e)



def timeit(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.info(f"Function {func.__name__} took {int(end-start)}s of time....")
        return result
    return wrapper

import asyncio, functools, random, time
from utils.logger import app_logger as logger

def retry_with_backoff(
    retries=3, 
    backoff_in_seconds=1, 
    max_backoff_in_seconds=60, 
    exceptions=(Exception,), 
    jitter=True
):
    """Retry sync or async functions with exponential backoff."""
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            delay = backoff_in_seconds
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs) if is_async else func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries:
                        logger.error(f"{func.__name__} failed after {retries} retries.")
                        raise
                    sleep = min(delay, max_backoff_in_seconds)
                    if jitter:
                        sleep *= (0.5 + random.random() / 2)
                    logger.warning(f"{func.__name__} attempt {attempt} failed: {e}. Retrying in {sleep:.1f}s...")
                    await asyncio.sleep(sleep) if is_async else time.sleep(sleep)
                    delay *= 2

        return async_wrapper
    return decorator


def get_secret(secret_name: str, region_name: str = "us-east-1"):
    # Create a Secrets Manager client
    client = boto3.client("secretsmanager", region_name=region_name)

    try:
        # Get the secret value
        response = client.get_secret_value(SecretId=secret_name)

        # The secret can be either a string or binary
        if "SecretString" in response:
            secret = response["SecretString"]
            return json.loads(secret)  # Parse JSON string if applicable
        else:
            # Decode binary secret
            secret = response["SecretBinary"]
            return secret.decode("utf-8")

    except Exception as e:
        logger.error(f"The requested secret {secret_name} was not found")

def seconds_to_hhmmss(seconds: int) -> str:
    """
    Convert seconds to HH:MM:SS format.

    Args:
        seconds: Number of seconds (int or float)

    Returns:
        str: Timecode string in HH:MM:SS
    """
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def is_video_url(url: str, timeout: int = 8) -> bool:
    """
    Check if the given URL is accessible and serves actual video content.
    """
    try:
        # Use HEAD first — lighter request
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        content_type = response.headers.get("Content-Type", "").lower()

        # If no content-type or it's generic, fallback to GET (some servers block HEAD)
        if not content_type or "text/html" in content_type:
            response = requests.get(url, stream=True, allow_redirects=True, timeout=timeout)
            content_type = response.headers.get("Content-Type", "").lower()

        # ✅ Confirm it's accessible and serves video content
        if response.status_code == 200 and any(ct in content_type for ct in VIDEO_CONTENT_TYPES):
            return True

        return False

    except requests.RequestException:
        return False