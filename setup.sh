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

# Create config file ONLY if it doesn't exist
# DO NOT overwrite if it already exists!
if [ ! -f "src/config.py" ]; then
    echo "Creating config file template..."
    cat > src/config.py << 'EOF'
# Instagram Account - SET THESE IN GITHUB SECRETS!
# DO NOT HARDCODE VALUES HERE!
INSTAGRAM_USERNAME = ""  # Will be set by GitHub Secrets
INSTAGRAM_PASSWORD = ""  # Will be set by GitHub Secrets

# Google Drive Configuration - SET THESE IN GITHUB SECRETS!
GDRIVE_FOLDER_ID = ""  # Will be set by GitHub Secrets

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
    echo "Note: Credentials should be set via GitHub Secrets, not in this file"
else
    echo "⚠️  config.py already exists. Not overwriting."
fi

# Test FFmpeg installation
echo "Testing FFmpeg installation..."
ffmpeg -version >/dev/null 2>&1 && echo "✓ FFmpeg is working" || echo "✗ FFmpeg not working"

echo ""
echo "✅ Setup complete!"
echo ""
echo "For GitHub Actions:"
echo "1. Set these GitHub Secrets:"
echo "   - INSTAGRAM_USERNAME"
echo "   - INSTAGRAM_PASSWORD"
echo "   - GDRIVE_FOLDER_ID"
echo "   - GDRIVE_CREDENTIALS"
echo "2. Workflow will override empty values"
