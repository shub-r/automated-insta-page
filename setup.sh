#!/bin/bash

echo "🚀 Instagram Auto-Poster Setup"
echo "================================"

# Check for required tools
command -v python3 >/dev/null 2>&1 || { echo "Python3 is required but not installed. Aborting."; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { 
    echo "FFmpeg is required but not installed."
    echo "Installing FFmpeg..."
    sudo apt update && sudo apt install -y ffmpeg || {
        echo "Failed to install FFmpeg. Please install manually:"
        echo "Ubuntu/Debian: sudo apt install ffmpeg"
        echo "macOS: brew install ffmpeg"
        exit 1
    }
}

# Create virtual environment (optional)
read -p "Create virtual environment? (y/n): " create_venv
if [[ $create_venv == "y" || $create_venv == "Y" ]]; then
    python3 -m venv venv
    source venv/bin/activate
    echo "Virtual environment activated"
fi

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r src/requirements.txt

# Create directories
echo "Creating necessary directories..."
mkdir -p downloads segments temp state

# Create config file if it doesn't exist
if [ ! -f "src/config.py" ]; then
    echo "Creating config file template..."
    cat > src/config.py << 'EOF'
# Instagram Account
INSTAGRAM_USERNAME = "your_instagram_username"
INSTAGRAM_PASSWORD = "your_instagram_password"

# Google Drive Configuration
GDRIVE_FOLDER_ID = "your_google_drive_folder_id"
GDRIVE_CREDENTIALS_FILE = "gdrive_credentials.json"

# Video Processing Settings
VIDEO_SEGMENT_MAX_DURATION = 170  # 2 minutes 50 seconds
SPEED_FACTOR = 1.25
MIN_SEGMENT_DURATION = 30
MAX_ORIGINAL_VIDEO_LENGTH = 3600  # 1 hour

# Posting Settings
POST_DAILY = True
POST_TIME = "09:00"
MAX_RETRIES = 3
DELAY_BETWEEN_POSTS = 60

# Instagram Limits
INSTAGRAM_MAX_VIDEO_DURATION = 180  # 3 minutes
INSTAGRAM_MAX_VIDEO_SIZE_MB = 100

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "instagram_poster.log"

# Error Handling
SKIP_PROBLEMATIC_VIDEOS = True
MAX_ERRORS_BEFORE_STOP = 5
EOF
    echo "Please edit src/config.py with your credentials"
fi

# Create Google Drive credentials file if needed
if [ ! -f "src/gdrive_credentials.json" ]; then
    echo "Please create src/gdrive_credentials.json with your Google Drive service account JSON"
fi

# Test FFmpeg installation
echo "Testing FFmpeg installation..."
ffmpeg -version >/dev/null 2>&1 && echo "✓ FFmpeg is working" || echo "✗ FFmpeg not working"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit src/config.py with your Instagram credentials"
echo "2. Add your Google Drive credentials as src/gdrive_credentials.json"
echo "3. Test locally: python src/main.py"
echo "4. Push to GitHub and set up secrets"