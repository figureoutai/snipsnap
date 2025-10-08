def get_audio_filename(idx: int):
    return f"audio_{idx:06d}.wav"

def get_video_frame_filename(idx: int):
    return f"frame_{idx:09d}.jpg"


def save_audio(audio_frames, sr, layout, output_path="output.wav"):
    import av
    import numpy as np
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
