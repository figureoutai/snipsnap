import os
import time
import uuid
import json
import boto3
import signal
import asyncio
import threading
import multiprocessing

from queue import Queue
from urllib.parse import urlparse
from utils.helpers import seconds_to_hhmmss
from utils.logger import app_logger as logger
from audio_transcriber import AudioTranscriber
from clip_scorer_service import ClipScorerService
from assort_clips_service import AssortClipsService
from repositories.aurora_service import AuroraService
from stream_processor.processor import StreamProcessor
from stream_processor.video_processor import VideoProcessor
from stream_processor.audio_processor import AudioProcessor
from config import BASE_DIR, STREAM_METADATA_TABLE, MEDIACONVERT_ROLE_ARN, AWS_REGION, S3_BUCKET_NAME, MAX_STREAM_DURATION


db_service = AuroraService()

async def set_stream_status(stream_id, status: str, message: str = None):
    await db_service.update_dict(
        STREAM_METADATA_TABLE, 
        {"status": status, "message": message}, 
        where_clause="stream_id=%s", 
        where_params=(stream_id,)
    )

def convert_to_hls_and_store(
    input_source: str,
    output_bucket: str,
    output_prefix: str,
    region: str = AWS_REGION
):
    """
    Convert a local video file or stream URL to HLS and upload to S3 using AWS MediaConvert.

    Args:
        input_source: Local file path or remote URL (http/https/s3).
        output_bucket: S3 bucket where converted files will be stored.
        output_prefix: Folder/prefix for the output HLS files.
        region: AWS region (default: us-east-1)
    """
    logger.info("[HLSConversion] starting the process to convert stream to HLS...")
    
    parsed = urlparse(input_source)
    if parsed.scheme.startswith("http"):
        input_s3_url = input_source
    else:
        raise ValueError("input_source must be HTTP URL")

    mediaconvert_client = boto3.client("mediaconvert", region_name=region)
    endpoint = mediaconvert_client.describe_endpoints()["Endpoints"][0]["Url"]
    mediaconvert = boto3.client("mediaconvert", endpoint_url=endpoint, region_name=region)

    destination = f"s3://{output_bucket}/{output_prefix}/"
    end_time = seconds_to_hhmmss(MAX_STREAM_DURATION)

    job_settings = {
        "TimecodeConfig": {
            "Source": "ZEROBASED"
        },
        "OutputGroups": [
            {
                "CustomName": "some-name",
                "Name": "Apple HLS",
                "Outputs": [
                    {
                        "ContainerSettings": {
                            "Container": "M3U8",
                            "M3u8Settings": {}
                        },
                        "VideoDescription": {
                        "CodecSettings": {
                            "Codec": "H_264",
                                "H264Settings": {
                                "MaxBitrate": 100000,
                                "RateControlMode": "QVBR",
                                "SceneChangeDetect": "TRANSITION_DETECTION"
                            }
                        }
                        },
                        "AudioDescriptions": [
                        {
                            "AudioSourceName": "Audio Selector 1",
                            "CodecSettings": {
                                "Codec": "AAC",
                                "AacSettings": {
                                    "Bitrate": 96000,
                                    "CodingMode": "CODING_MODE_2_0",
                                    "SampleRate": 48000
                                }
                            }
                        }
                        ],
                        "OutputSettings": {
                            "HlsSettings": {}
                        },
                        "NameModifier": "_"
                    }
                ],
                "OutputGroupSettings": {
                    "Type": "HLS_GROUP_SETTINGS",
                    "HlsGroupSettings": {
                        "SegmentLength": 10,
                        "Destination": destination,
                        "DestinationSettings": {
                            "S3Settings": {
                                "StorageClass": "STANDARD"
                            }
                        },
                        "MinSegmentLength": 0
                    }
                }
            }
        ],
        "FollowSource": 1,
        "Inputs": [
            {
                "AudioSelectors": {
                    "Audio Selector 1": {
                        "DefaultSelection": "DEFAULT"
                    }
                },
                "VideoSelector": {},
                "TimecodeSource": "ZEROBASED",
                "FileInput": input_source,
                "InputClippings": [
                    {
                        "EndTimecode": f"{end_time}:00"
                    }
                ]
            }
        ]
    }

    logger.info("[HLSConversion] pushing mediaconvert job...")

    response = mediaconvert.create_job(
        Role=MEDIACONVERT_ROLE_ARN,
        Settings=job_settings
    )

    logger.info(f"✅ MediaConvert job started: {response["Job"]["Id"]}, for input {input_s3_url} and output will be stored in {destination}..")



async def main():
    logger.info("[Main] trying to read the message from environment....")
    # Parse job message
    JOB_MESSAGE = os.environ.get("JOB_MESSAGE")
    if JOB_MESSAGE is None:
        logger.info("No JOB_MESSAGE provided. Exiting without work.")
        return

    try:
        parsed_msg = json.loads(JOB_MESSAGE)
    except (TypeError, json.JSONDecodeError):
        logger.error("No JOB_MESSAGE provided. Exiting without work.")
        return

    logger.info(f"[Main] parsed job message.... {parsed_msg}")
    
    logger.info("[Main] connecting to db...")
    await db_service.initialize()
    logger.info("[Main] successfully connected to db...")

    stream_id = parsed_msg["stream_id"] if parsed_msg["stream_id"] else f"{uuid.uuid4()}"
    stream_url = parsed_msg["stream_url"] if parsed_msg["stream_url"] else "./data/test_videos/news.mp4"

    await set_stream_status(stream_id, "IN_PROGRESS")

    job_params = {
        "input_source": stream_url,
        "output_bucket": S3_BUCKET_NAME,
        "output_prefix": f"streams/{stream_id}/video",
    }
    process = multiprocessing.Process(target=convert_to_hls_and_store, kwargs=job_params)
    process.start()

    start_time = time.time()
    # To signal async functions for stop
    stream_processor_event = threading.Event()
    video_processor_event = asyncio.Event()
    audio_processor_event = asyncio.Event()
    clip_scorer_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    audio_frame_q = Queue(maxsize=2048)
    video_frame_q = Queue(maxsize=2048)
    stream_processor = StreamProcessor(stream_url, audio_frame_q, video_frame_q)
    video_processor = VideoProcessor(f"{BASE_DIR}/{stream_id}/frames", video_frame_q)
    audio_processor = AudioProcessor(f"{BASE_DIR}/{stream_id}/audio_chunks", audio_frame_q)
    audio_transcriber = AudioTranscriber(f"{BASE_DIR}/{stream_id}/audio_chunks")
    clip_scorer = ClipScorerService()
    assort_clips_service = AssortClipsService()


    stream_task = threading.Thread(target=stream_processor.start_stream, args=(stream_processor_event,), daemon=True)
    stream_task.start()

    tasks = [
        asyncio.create_task(video_processor.process_frames(stream_id, video_processor_event, stream_processor_event)),
        asyncio.create_task(audio_processor.process_frames(stream_id, audio_processor_event, stream_processor_event)),
        asyncio.create_task(audio_transcriber.transcribe_audio(stream_id, audio_processor_event)),
        asyncio.create_task(clip_scorer.score_clips(stream_id, clip_scorer_event, audio_processor_event, video_processor_event)),
        asyncio.create_task(assort_clips_service.assort_clips(stream_id, clip_scorer_event))
    ]

    def _signal_handler(signum, frame):
        print(f"Received signal {signum}; initiating shutdown.")
        stream_processor_event.set()
        loop.call_soon_threadsafe(video_processor_event.set)
        loop.call_soon_threadsafe(audio_processor_event.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _signal_handler)

    try:
        await asyncio.wait(
            [asyncio.gather(*tasks)],
            return_when=asyncio.ALL_COMPLETED
        )
        if all([video_processor_event.is_set(), audio_processor_event.is_set()]):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await set_stream_status(stream_id, "COMPLETED")
    except Exception as e:
        await set_stream_status(stream_id, "FAILED", str(e))
    finally:
        stream_processor_event.set()
        await db_service.close()
        print("Shutdown complete.")
        end_time = time.time()
        logger.info(f"[Main] Total time taken by pipeline is: {end_time-start_time}s", )


if __name__ == "__main__":
    logger.info("Starting the pipeline....")
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(e)
