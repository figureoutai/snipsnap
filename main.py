import time
import uuid
import signal
import asyncio
import threading

from utils.logger import app_logger as logger
from audio_transcriber import AudioTranscriber
from utils.unique_async_queue import UniqueAsyncQueue
from stream_processor.processor import StreamProcessor
from stream_processor.video_processor import VideoProcessor
from stream_processor.audio_processor import AudioProcessor

async def main():
    stream_id = f'{uuid.uuid4()}'
    start_time = time.time()
    # To signal async functions for stop
    async_stop = asyncio.Event()
    thread_stop = threading.Event()
    loop = asyncio.get_running_loop()

    audio_frame_q = UniqueAsyncQueue()
    video_frame_q = UniqueAsyncQueue()
    stream_processor = StreamProcessor("./data/test_videos/apple.mp4", audio_frame_q, video_frame_q)
    video_processor = VideoProcessor(f"./data/{stream_id}/frames", video_frame_q)
    audio_processor = AudioProcessor(f"./data/{stream_id}/audio_chunks", audio_frame_q)
    audio_transcriber = AudioTranscriber()

    stream_task = threading.Thread(target=stream_processor.start_stream, args=(thread_stop,), daemon=True)
    stream_task.start()

    tasks = [
        asyncio.create_task(video_processor.process_frames(stream_id, async_stop)),
        asyncio.create_task(audio_processor.process_frames(stream_id, async_stop)),
        # asyncio.create_task(audio_transcriber.transcribe_audio(async_stop))
    ]

    def _signal_handler(signum, frame):
        print(f"Received signal {signum}; initiating shutdown.")
        thread_stop.set()
        loop.call_soon_threadsafe(async_stop.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _signal_handler)

    try:
        await asyncio.wait(
            [asyncio.gather(*tasks), asyncio.shield(async_stop.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )
        if async_stop.is_set():
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        thread_stop.set()
        print("Shutdown complete.")
        end_time = time.time()
        logger.info(f"Total time taken by pipeline is: {end_time-start_time}s", )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(e)
