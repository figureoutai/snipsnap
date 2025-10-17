import os
AWS_REGION = "us-east-1"
LANGUAGE_CODE="en-US"

S3_BUCKET_NAME = "highlight-clipping-service-main-975049899047"
S3_REGION = "us-east-1"
IMAGE_BUCKET_PREFIX = "images/frame/"
AUDIO_BUCKET_PREFIX = "audio/streams/"

# Optional: CloudFront domain to serve S3 objects
CDN_DOMAIN = os.environ.get("CDN_DOMAIN")


DB_NAME=os.environ.get("DB_NAME", "video_processing_db")
VIDEO_METADATA_TABLE_NAME = "video_metadata"
AUDIO_METADATA_TABLE_NAME = "audio_metadata"
SCORE_METADATA_TABLE = "score_metadata"
STREAM_METADATA_TABLE = "stream_metadata"

DB_HOST = os.environ.get("DB_URL", "localhost") #"highlight-clipping-service-main-auroracluster-o27b01gfhdja.cluster-ckdseak4qyg6.us-east-1.rds.amazonaws.com")
DB_PORT = 3306
DB_SECRET_NAME = os.environ.get("SECRET_NAME", "rds!cluster-00500b97-b996-4bb1-9e88-00aef1715034")

# AUDIO CONFIGURATION
TARGET_SAMPLE_RATE = 16000
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

HIGHLIGHT_CHUNK = 300
MAX_STREAM_DURATION = 10

# --- Agentic Boundary Snapping (defaults) ---
# Max allowed edge shifts when snapping to boundaries (seconds)
SNAP_MAX_SHIFT_SCENE_START = 1.0
SNAP_MAX_SHIFT_SCENE_END = 2.0
SNAP_MAX_SHIFT_TOPIC = 1.0

# Enforce clip duration bounds after snapping (seconds)
HIGHLIGHT_MIN_LEN = 4.0
HIGHLIGHT_MAX_LEN = 12.0

# TextTiling parameters (topic segmentation over ASR words)
TEXT_TILING_BLOCK = 20
TEXT_TILING_STEP = 10
TEXT_TILING_SMOOTH = 2
TEXT_TILING_CUTOFF_STD = 0.5

# LLM arbitration for snapped vs original highlights (assort stage)
LLM_SNAP_ARBITRATE = True
LLM_SNAP_MIN_DELTA_SEC = 0.6
LLM_SNAP_MAX_ATTEMPTS = 3
LLM_SNAP_CONFIDENCE_THRESHOLD = 0.7
