import os
import time
import uuid
import json
import signal
import asyncio
import threading

from queue import Queue
from utils.logger import app_logger as logger
from audio_transcriber import AudioTranscriber
from clip_scorer_service import ClipScorerService
from config import BASE_DIR, STREAM_METADATA_TABLE
from assort_clips_service import AssortClipsService
from repositories.aurora_service import AuroraService
from stream_processor.processor import StreamProcessor
from stream_processor.video_processor import VideoProcessor
from stream_processor.audio_processor import AudioProcessor

db_service = AuroraService()

async def set_stream_status(stream_id, status: str, message: str = None):
    await db_service.update_dict(
        STREAM_METADATA_TABLE, 
        {"status": status, "message": message}, 
        where_clause="stream_id=%s", 
        where_params=(stream_id,)
    )

async def main():
    logger.info("[Main] trying to read the message from environment....")
    # Parse job message
    # JOB_MESSAGE = os.environ.get("JOB_MESSAGE")
    # if JOB_MESSAGE is None:
    #     logger.info("No JOB_MESSAGE provided. Exiting without work.")
    #     return

    try:
        parsed_msg = {
            "stream_id": f"{uuid.uuid4()}",
            "stream_url": "./data/test_videos/news.mp4"
        }
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
