"""
Configuration for Instagram Auto-Poster
DO NOT commit this file with real credentials
"""

# Instagram Account
INSTAGRAM_USERNAME = "watch.fun.world"  # Your Instagram username
INSTAGRAM_PASSWORD = "at_pg_users.xmlshub129"  # Your Instagram password

# Google Drive Configuration
GDRIVE_FOLDER_ID = "1eAU51t7yGLs9CJLZ1EfhJtsJZhdbg7FO"  # From your Drive URL
GDRIVE_CREDENTIALS_FILE = "gdrive_credentials.json"  # Will be created from secret

# Video Processing Settings
VIDEO_SEGMENT_MAX_DURATION = 170  # Maximum 2 minutes 50 seconds (170 seconds)
SPEED_FACTOR = 1.25  # Speed multiplier (1.25x)
MIN_SEGMENT_DURATION = 30  # Minimum segment duration in seconds
MAX_ORIGINAL_VIDEO_LENGTH = 3600  # Skip videos longer than 1 hour

# Posting Settings
POST_DAILY = True  # Post one video per day
POST_TIME = "09:00"  # Daily posting time (UTC)
MAX_RETRIES = 3  # Maximum retries for failed operations
DELAY_BETWEEN_POSTS = 60  # Seconds between posts (if posting multiple segments)

# Instagram Limits
INSTAGRAM_MAX_VIDEO_DURATION = 180  # 3 minutes in seconds
INSTAGRAM_MAX_VIDEO_SIZE_MB = 100  # Maximum video size

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "instagram_poster.log"

# Error Handling
SKIP_PROBLEMATIC_VIDEOS = True  # Skip videos that cause errors
MAX_ERRORS_BEFORE_STOP = 5  # Stop after this many consecutive errors