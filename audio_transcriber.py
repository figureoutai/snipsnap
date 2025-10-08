import os
import asyncio
import aiofiles

from asyncio import Event
from config import AUDIO_CHUNK_DIR, AWS_REGION, LANGUAGE_CODE
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent, StartStreamTranscriptionEventStream


class TranscriptEventHandler(TranscriptResultStreamHandler):
    def __init__(self, stream_id, filename, output_stream):
        super().__init__(output_stream)
        self.transcript_data = []
        self.filename = filename
        self.stream_id = stream_id

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            if result.alternatives and not result.is_partial:
                for item in result.alternatives[0].items:
                    item_data = {
                        "start_time": item.start_time,
                        "end_time": item.end_time,
                        "content": item.content,
                        "type": item.item_type,
                    }
                    self.transcript_data.append(item_data)
        # TODO: Update transcript data in aurora db
        # await run_sync_func(update_audio_transcript, self.filename, self.transcript_data)


class AudioTranscriber:
    def __init__(self):
        self.client = TranscribeStreamingClient(region=AWS_REGION)

    async def transcribe_audio(self, stop_event: Event):
        while True:
            if stop_event.is_set():
                break
            
            # TODO: Get Audio Chunks metadata from aurora db, limit 10
            audio_chunks = []

            for chunk in audio_chunks:
                filepath = os.path.join(AUDIO_CHUNK_DIR, chunk["filename"])
                sample_rate = chunk["sample_rate"]
                stream_id = chunk["stream_id"]
                transcription_stream = await self.client.start_stream_transcription(
                    language_code=LANGUAGE_CODE,
                    media_sample_rate_hz=sample_rate,
                    media_encoding="pcm",
                )

                filename = os.path.basename(filepath)
                event_handler = TranscriptEventHandler(stream_id, filename, transcription_stream.output_stream )
                await asyncio.gather(self.send_audio_chunks(filepath, transcription_stream), event_handler.handle_events())

            await asyncio.sleep(2)

    async def send_audio_chunks(filepath: str, transcription_stream: StartStreamTranscriptionEventStream):
        async with aiofiles.open(filepath, 'rb') as audio_file:
            chunk_size = 1024 * 16
            while True:
                chunk = await audio_file.read(chunk_size)
                if not chunk:
                    break
                await transcription_stream.input_stream.send_audio_event(audio_chunk=chunk)
        await transcription_stream.input_stream.end_stream()
