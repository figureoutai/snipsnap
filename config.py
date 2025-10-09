AWS_REGION = "us-east-1"
LANGUAGE_CODE="en"

S3_BUCKET_NAME = "clip-highlights-bucket"
S3_REGION = "us-east-1"
IMAGE_BUCKET_PREFIX = "images/frame/"
AUDIO_BUCKET_PREFIX = "audio/streams/"


DB_NAME="clip_metadata"
VIDEO_METADATA_TABLE_NAME = "video_metadata"
AUDIO_METADATA_TABLE_NAME = "audio_metadata"
SCORE_METADATA_TABLE = "score_metadata"

DB_HOST = "clip-highlights-instance-1.cdgkfoacvf6u.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "<admin-password>"
DB_PORT = 3306

# AUDIO CONFIGURATION
TARGET_SAMPLE_RATE = 16000
AUDIO_CHUNK_DIR = ""
AUDIO_CHUNK = 5

# VIDEO CONFIGURATION
VIDEO_FRAME_SAMPLE_RATE = 2

# SALIENCY CONFIGURATION
SALIENCY_THRESHOLD = 0.7


# SLICE
CANDIDATE_SLICE = 5
STEP_BACK = 2

# LOCAL STORAGE
BASE_DIR = "./data"

MAX_STREAM_DURATION = 600