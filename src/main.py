#!/usr/bin/env python3
"""
Instagram Auto-Poster - Debug Version
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    # Import configuration
    from config import *
    print(f"✅ Config loaded from config.py")
    print(f"   Username: {INSTAGRAM_USERNAME}")
    print(f"   Folder ID: {GDRIVE_FOLDER_ID}")
    print(f"   Folder ID length: {len(GDRIVE_FOLDER_ID)}")
except ImportError as e:
    print(f"❌ Failed to import config: {e}")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_poster.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def test_google_drive():
    """Test Google Drive connection"""
    logger.info("🔍 Testing Google Drive connection...")
    
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # Load credentials from environment
        gdrive_creds = os.getenv("GDRIVE_CREDENTIALS")
        if not gdrive_creds:
            logger.error("GDRIVE_CREDENTIALS not found in environment")
            return False
        
        creds_info = json.loads(gdrive_creds)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        
        # Test folder access
        logger.info(f"Testing access to folder: {GDRIVE_FOLDER_ID}")
        
        try:
            folder = service.files().get(fileId=GDRIVE_FOLDER_ID, fields='id,name').execute()
            logger.info(f"✅ Folder found: {folder.get('name')}")
        except Exception as e:
            logger.error(f"❌ Folder not found: {e}")
            return False
        
        # List files
        query = f"'{GDRIVE_FOLDER_ID}' in parents and mimeType contains 'video/'"
        logger.info(f"Query: {query}")
        
        results = service.files().list(
            q=query,
            pageSize=10,
            fields="files(id, name, mimeType, size)",
            orderBy="name"
        ).execute()
        
        videos = results.get('files', [])
        logger.info(f"✅ Found {len(videos)} video files")
        
        for i, video in enumerate(videos):
            size_mb = int(video.get('size', 0)) / (1024*1024)
            logger.info(f"  {i+1}. {video['name']} ({size_mb:.1f} MB)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Google Drive test failed: {e}")
        return False

def test_instagram():
    """Test Instagram connection"""
    logger.info("🔍 Testing Instagram connection...")
    
    try:
        from instagrapi import Client
        
        cl = Client()
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        
        user_id = cl.user_id
        logger.info(f"✅ Instagram login successful! User ID: {user_id}")
        
        # Get user info
        user_info = cl.user_info(user_id)
        logger.info(f"   Username: {user_info.username}")
        logger.info(f"   Followers: {user_info.follower_count}")
        
        cl.logout()
        return True
        
    except Exception as e:
        logger.error(f"❌ Instagram test failed: {e}")
        return False

def main():
    """Main function"""
    logger.info("=" * 60)
    logger.info("INSTAGRAM AUTO-POSTER - DEBUG MODE")
    logger.info("=" * 60)
    
    # Log current configuration
    logger.info(f"Configuration loaded:")
    logger.info(f"  Instagram Username: {INSTAGRAM_USERNAME}")
    logger.info(f"  Google Drive Folder ID: {GDRIVE_FOLDER_ID}")
    logger.info(f"  Video Segment Duration: {VIDEO_SEGMENT_MAX_DURATION}s")
    logger.info(f"  Speed Factor: {SPEED_FACTOR}x")
    
    # Test connections
    if not test_google_drive():
        logger.error("Google Drive test failed. Exiting.")
        return
    
    if not test_instagram():
        logger.error("Instagram test failed. Exiting.")
        return
    
    logger.info("=" * 60)
    logger.info("✅ All tests passed! Ready for posting.")
    logger.info("=" * 60)
    
    # Here you would continue with your actual posting logic
    # For now, just exit successfully
    logger.info("Debug mode complete. Exiting.")

if __name__ == "__main__":
    main()
