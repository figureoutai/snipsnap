import asyncio

from stream_processor.processor import StreamProcessor
from stream_processor.video_processor import VideoProcessor
from utils.unique_async_queue import UniqueAsyncQueue
from utils.logger import app_logger as logger

async def main():
    audio_frame_q = UniqueAsyncQueue()
    video_frame_q = UniqueAsyncQueue()
    stream_processor = StreamProcessor("./data/test_videos/news.mp4", audio_frame_q, video_frame_q)
    video_processor = VideoProcessor("./data/frames", video_frame_q)
    tasks = [
        asyncio.create_task(stream_processor.start_stream()),
        asyncio.create_task(video_processor.sample_frames())
    ]

    await asyncio.wait(
        [asyncio.gather(*tasks)],
        return_when=asyncio.FIRST_COMPLETED
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(e)
