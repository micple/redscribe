"""
Application configuration constants.
"""
import os
from pathlib import Path

# Application info
APP_NAME = "Redscribe"
APP_VERSION = "1.0.0"

# Paths
APPDATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
CONFIG_FILE = APPDATA_DIR / "config.json"
LOGS_DIR = APPDATA_DIR / "logs"
TEMP_DIR = Path(os.environ.get("TEMP", "/tmp")) / APP_NAME.lower()

# Ensure directories exist
APPDATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Supported file extensions
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm", ".flv"}
ALL_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

# FFmpeg conversion settings
FFMPEG_AUDIO_CODEC = "libmp3lame"
FFMPEG_SAMPLE_RATE = 16000  # Optimal for speech recognition
FFMPEG_CHANNELS = 1  # Mono
FFMPEG_BITRATE = "64k"

# Deepgram API settings
DEEPGRAM_DEFAULT_MODEL = "nova-2"
DEEPGRAM_DEFAULT_SPECIALIZATION = "general"
DEEPGRAM_MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

# Available models
DEEPGRAM_MODELS = {
    "nova-2": "Nova-2 (Recommended)",
    "nova-3": "Nova-3 (Premium)",
}

# Specializations per model
DEEPGRAM_SPECIALIZATIONS = {
    "nova-2": {
        "general": "General",
        "meeting": "Meeting",
        "phonecall": "Phonecall",
        "voicemail": "Voicemail",
        "finance": "Finance",
        "conversationalai": "Conversational AI",
        "video": "Video",
        "medical": "Medical",
        "drivethru": "Drive-thru",
        "automotive": "Automotive",
        "atc": "Air Traffic Control",
    },
    "nova-3": {
        "general": "General",
        "medical": "Medical",
    },
}

# Supported languages (code: display name)
SUPPORTED_LANGUAGES = {
    "auto": "Auto-detect",
    "pl": "Polski",
    "en": "English",
    "de": "Deutsch",
    "fr": "Fran\u00e7ais",
    "es": "Espa\u00f1ol",
    "it": "Italiano",
    "pt": "Portugu\u00eas",
    "nl": "Nederlands",
    "ru": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "uk": "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430",
    "ja": "\u65e5\u672c\u8a9e",
    "zh": "\u4e2d\u6587",
}

# Output formats
OUTPUT_FORMATS = ["txt", "srt", "vtt"]

# Network settings
API_TIMEOUT = 300  # 5 minutes
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# GUI settings
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600
