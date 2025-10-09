import re
import cv2
import json
import time
import base64
import asyncio
import random
import functools
import numpy as np

from .logger import app_logger as logger

EMPTY_STRING = "EMPTY"


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


def retry_with_backoff(
    retries=3,
    backoff_in_seconds=1,
    max_backoff_in_seconds=60,
    exceptions=(Exception,),
    jitter=True,
):
    """
    Decorator to retry a function with exponential backoff.
    
    Args:
        retries (int): Number of retry attempts before giving up.
        backoff_in_seconds (int): Initial backoff delay in seconds.
        max_backoff_in_seconds (int): Max sleep time between retries.
        exceptions (tuple): Exceptions to catch for retry.
        jitter (bool): If True, add randomness to backoff (recommended).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = backoff_in_seconds
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries:
                        logger.error(f"Function {func.__name__} failed after {retries} attempts.")
                        raise
                    else:
                        sleep_time = min(delay, max_backoff_in_seconds)
                        if jitter:
                            sleep_time = sleep_time * (0.5 + random.random() / 2)  # ±50%
                        logger.warning(
                            f"Attempt {attempt} failed with {e}. "
                            f"Retrying in {sleep_time:.2f} seconds..."
                        )
                        time.sleep(sleep_time)
                        delay *= 2  # Exponential backoff
        return wrapper
    return decorator
