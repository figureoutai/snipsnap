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
    stream_processor_event = threading.Event()
    video_processor_event = asyncio.Event()
    audio_processor_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    audio_frame_q = UniqueAsyncQueue()
    video_frame_q = UniqueAsyncQueue()
    stream_processor = StreamProcessor("./data/test_videos/apple.mp4", audio_frame_q, video_frame_q)
    video_processor = VideoProcessor(f"./data/{stream_id}/frames", video_frame_q)
    audio_processor = AudioProcessor(f"./data/{stream_id}/audio_chunks", audio_frame_q)
    audio_transcriber = AudioTranscriber()

    stream_task = threading.Thread(target=stream_processor.start_stream, args=(stream_processor_event,), daemon=True)
    stream_task.start()

    tasks = [
        asyncio.create_task(video_processor.process_frames(stream_id, video_processor_event, stream_processor_event)),
        asyncio.create_task(audio_processor.process_frames(stream_id, audio_processor_event, stream_processor_event)),
        # asyncio.create_task(audio_transcriber.transcribe_audio(async_stop))
    ]

    def _signal_handler(signum, frame):
        print(f"Received signal {signum}; initiating shutdown.")
        stream_processor.set()
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
    finally:
        stream_processor_event.set()
        print("Shutdown complete.")
        end_time = time.time()
        logger.info(f"Total time taken by pipeline is: {end_time-start_time}s", )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(e)
