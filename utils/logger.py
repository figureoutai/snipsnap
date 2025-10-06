import logging

# Default format for all loggers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Custom logger for your app
app_logger = logging.getLogger("video-highlights")
handler = logging.FileHandler("video-highlights-pipeline.log")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s",  datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
app_logger.addHandler(handler)