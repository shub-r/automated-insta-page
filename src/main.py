#!/usr/bin/env python3
"""
Instagram Auto-Poster
Posts videos from Google Drive to Instagram Reels automatically
"""

import os
import sys
import json
import time
import logging
import tempfile
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import urllib.parse

# Third-party imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import requests

# Local imports
from config import (
    FACEBOOK_ACCESS_TOKEN,
    FACEBOOK_USER_ID,
    GDRIVE_FOLDER_ID,
    GDRIVE_CREDENTIALS_PATH,
    MANUAL_DAY_OVERRIDE,
    MANUAL_PART_OVERRIDE
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_poster.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
FACEBOOK_GRAPH_URL = "https://graph.facebook.com/v18.0"
MAX_RETRIES = 3
MAX_CONSECUTIVE_ERRORS = 5
STATE_FILE = Path(__file__).parent.parent / "state" / "posting_state.json"

class InstagramAutoPoster:
    def __init__(self):
        self.consecutive_errors = 0
        self.current_state = self.load_state()
        
        # Initialize Google Drive API
        self.drive_service = self.init_google_drive()
        
        # Get Instagram Business Account ID
        self.instagram_account_id = self.get_instagram_account_id()
        if not self.instagram_account_id:
            logger.error("Could not get Instagram Business Account ID!")
            raise Exception("Instagram Business Account ID not found")
        
    def init_google_drive(self):
        """Initialize Google Drive API with service account"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                GDRIVE_CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            return build('drive', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive API: {e}")
            raise
    
    def get_instagram_account_id(self):
        """Get Instagram Business Account ID from Facebook Page"""
        try:
            # First, get the Facebook Page connected to the Instagram account
            pages_url = f"{FACEBOOK_GRAPH_URL}/me/accounts"
            params = {
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'fields': 'id,name,instagram_business_account'
            }
            
            response = requests.get(pages_url, params=params)
            response.raise_for_status()
            
            pages_data = response.json()
            logger.info(f"Pages data: {json.dumps(pages_data, indent=2)}")
            
            # Look for the page that has an Instagram Business Account connected
            for page in pages_data.get('data', []):
                if 'instagram_business_account' in page:
                    ig_business_account = page['instagram_business_account']
                    ig_account_id = ig_business_account.get('id') if isinstance(ig_business_account, dict) else ig_business_account
                    
                    if ig_account_id:
                        logger.info(f"Found Instagram Business Account ID: {ig_account_id}")
                        return ig_account_id
            
            # If we have a specific user ID provided, use it directly
            if FACEBOOK_USER_ID:
                logger.info(f"Using provided Facebook User ID: {FACEBOOK_USER_ID}")
                return FACEBOOK_USER_ID
                
            logger.error("No Instagram Business Account found connected to any Facebook Page")
            return None
            
        except Exception as e:
            logger.error(f"Error getting Instagram Account ID: {e}")
            logger.error(f"Response: {response.text if 'response' in locals() else 'No response'}")
            return None
    
    def load_state(self) -> Dict:
        """Load posting state from JSON file"""
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    logger.info(f"Loaded state: {state}")
                    return state
        except Exception as e:
            logger.error(f"Error loading state: {e}")
        
        # Default state
        default_state = {
            "current_day": 1,
            "current_part": 1,
            "last_posted": None,
            "total_posts": 0,
            "consecutive_errors": 0,
            "error_history": []
        }
        logger.info("Using default state")
        return default_state
    
    def save_state(self):
        """Save current state to JSON file"""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(self.current_state, f, indent=2)
            logger.info(f"State saved: {self.current_state}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def list_day_folders(self) -> List[str]:
        """List all day folders in the Google Drive folder"""
        try:
            query = f"'{GDRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            # Sort folders by name (day1, day2, etc.)
            sorted_folders = sorted(folders, key=lambda x: x['name'])
            folder_names = [f['name'] for f in sorted_folders]
            
            logger.info(f"Found {len(folder_names)} day folders: {folder_names}")
            return folder_names
            
        except Exception as e:
            logger.error(f"Error listing day folders: {e}")
            raise
    
    def get_videos_in_folder(self, folder_name: str) -> List[str]:
        """Get all video files in a specific day folder"""
        try:
            # First, get the folder ID
            folder_query = f"name='{folder_name}' and '{GDRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
            folder_result = self.drive_service.files().list(
                q=folder_query,
                fields="files(id)"
            ).execute()
            
            if not folder_result.get('files'):
                logger.error(f"Folder '{folder_name}' not found")
                return []
            
            folder_id = folder_result['files'][0]['id']
            
            # Get video files in the folder
            video_query = f"'{folder_id}' in parents and (mimeType contains 'video/' or name contains '.mp4')"
            results = self.drive_service.files().list(
                q=video_query,
                fields="files(id, name, mimeType)"
            ).execute()
            
            videos = results.get('files', [])
            # Sort by name (part1.mp4, part2.mp4, etc.)
            sorted_videos = sorted(videos, key=lambda x: x['name'])
            video_names = [v['name'] for v in sorted_videos]
            
            logger.info(f"Found {len(video_names)} videos in {folder_name}: {video_names}")
            return sorted_videos
            
        except Exception as e:
            logger.error(f"Error getting videos in folder {folder_name}: {e}")
            return []
    
    def download_video(self, video_info: Dict, download_path: Path) -> bool:
        """Download video from Google Drive to local path"""
        try:
            file_id = video_info['id']
            filename = video_info['name']
            
            request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(download_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.info(f"Download progress: {int(status.progress() * 100)}%")
            
            logger.info(f"Downloaded video: {filename} ({download_path.stat().st_size / 1024 / 1024:.2f} MB)")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            return False
    
    def create_instagram_container(self, video_path: Path, caption: str) -> Optional[str]:
        """Create Instagram container for video upload"""
        try:
            # Step 1: Upload video and create container
            container_url = f"{FACEBOOK_GRAPH_URL}/{self.instagram_account_id}/media"
            
            # First, check if we can access the Instagram account
            check_url = f"{FACEBOOK_GRAPH_URL}/{self.instagram_account_id}"
            check_params = {
                'fields': 'id,name,username',
                'access_token': FACEBOOK_ACCESS_TOKEN
            }
            
            check_response = requests.get(check_url, params=check_params)
            logger.info(f"Instagram account check: {check_response.status_code}")
            if check_response.status_code != 200:
                logger.error(f"Cannot access Instagram account: {check_response.text}")
                return None
            
            # Now create the container
            with open(video_path, 'rb') as video_file:
                files = {'video': video_file}
                data = {
                    'caption': caption,
                    'media_type': 'REELS',
                    'share_to_feed': True,
                    'access_token': FACEBOOK_ACCESS_TOKEN
                }
                
                logger.info(f"Creating container for video: {video_path.name}")
                logger.info(f"Container URL: {container_url}")
                
                response = requests.post(container_url, data=data, files=files, timeout=60)
                
                logger.info(f"Container creation response: {response.status_code}")
                logger.info(f"Container creation response text: {response.text}")
                
                response.raise_for_status()
                
                result = response.json()
                container_id = result.get('id')
                
                if container_id:
                    logger.info(f"Created container: {container_id}")
                    return container_id
                else:
                    logger.error(f"No container ID in response: {result}")
                    return None
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error creating Instagram container: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error creating Instagram container: {e}")
            return None
    
    def publish_container(self, container_id: str) -> bool:
        """Publish the Instagram container"""
        try:
            publish_url = f"{FACEBOOK_GRAPH_URL}/{self.instagram_account_id}/media_publish"
            
            data = {
                'creation_id': container_id,
                'access_token': FACEBOOK_ACCESS_TOKEN
            }
            
            for attempt in range(MAX_RETRIES):
                logger.info(f"Publishing container (attempt {attempt + 1}/{MAX_RETRIES})...")
                
                response = requests.post(publish_url, data=data)
                logger.info(f"Publish response: {response.status_code}")
                logger.info(f"Publish response text: {response.text}")
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('id'):
                        logger.info(f"Successfully published! Post ID: {result['id']}")
                        return True
                
                # If not successful, wait and retry
                if attempt < MAX_RETRIES - 1:
                    wait_time = 10 * (attempt + 1)  # Exponential backoff
                    logger.warning(f"Publish attempt failed, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
            
            logger.error(f"Failed to publish container after {MAX_RETRIES} attempts")
            return False
            
        except Exception as e:
            logger.error(f"Error publishing container: {e}")
            return False
    
    def generate_caption(self, day_number: int, part_number: int, total_parts: int) -> str:
        """Generate caption for the video post"""
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        caption = f"""Day {day_number} - Part {part_number}/{total_parts}

📅 Posted automatically on {current_date}
⚡ Powered by GitHub Actions & Facebook Graph API

#Day{day_number} #Part{part_number} #InstagramReels #AutoPost #Tech #AI #GitHubActions #Coding #Automation #Programming #DevOps #Python #FacebookAPI"""

        return caption
    
    def post_video_to_instagram(self, video_path: Path, caption: str) -> bool:
        """Main function to post video to Instagram"""
        try:
            # Check file size (Instagram limit is 100MB for Reels)
            file_size_mb = video_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 100:
                logger.error(f"Video file too large: {file_size_mb:.2f}MB (max 100MB)")
                return False
            
            # Check video duration (Instagram Reels limit is 90 seconds)
            # Note: We're assuming videos are pre-optimized
            
            # Step 1: Create container
            logger.info("Creating Instagram container...")
            container_id = self.create_instagram_container(video_path, caption)
            if not container_id:
                logger.error("Failed to create container")
                return False
            
            # Step 2: Wait a moment for processing
            logger.info("Waiting for video processing...")
            time.sleep(15)
            
            # Step 3: Publish container
            logger.info("Publishing container...")
            success = self.publish_container(container_id)
            
            if success:
                logger.info("Video published successfully!")
                # Wait a bit more for Instagram to process
                time.sleep(5)
            
            return success
            
        except Exception as e:
            logger.error(f"Error posting to Instagram: {e}")
            return False
    
    def determine_next_video(self) -> Tuple[Optional[str], Optional[Dict]]:
        """Determine which video to post next based on state"""
        # Check for manual overrides
        if MANUAL_DAY_OVERRIDE and MANUAL_DAY_OVERRIDE.isdigit():
            self.current_state["current_day"] = int(MANUAL_DAY_OVERRIDE)
            logger.info(f"Manual override: Setting day to {MANUAL_DAY_OVERRIDE}")
        
        if MANUAL_PART_OVERRIDE and MANUAL_PART_OVERRIDE.isdigit():
            self.current_state["current_part"] = int(MANUAL_PART_OVERRIDE)
            logger.info(f"Manual override: Setting part to {MANUAL_PART_OVERRIDE}")
        
        # Get all day folders
        day_folders = self.list_day_folders()
        if not day_folders:
            logger.error("No day folders found!")
            return None, None
        
        # Find current day folder
        current_day = self.current_state["current_day"]
        day_folder_name = f"day{current_day}"
        
        if day_folder_name not in day_folders:
            logger.warning(f"Day folder {day_folder_name} not found, resetting to day1")
            self.current_state["current_day"] = 1
            self.current_state["current_part"] = 1
            day_folder_name = "day1"
            current_day = 1
        
        # Get videos in current day folder
        videos = self.get_videos_in_folder(day_folder_name)
        if not videos:
            logger.error(f"No videos found in {day_folder_name}")
            return None, None
        
        # Find current part
        current_part = self.current_state["current_part"]
        video_name = f"part{current_part}.mp4"
        
        # Look for the video
        target_video = None
        for video in videos:
            if video['name'].lower() == video_name.lower():
                target_video = video
                break
        
        if not target_video:
            logger.warning(f"Video {video_name} not found in {day_folder_name}")
            
            # Check if we've completed all parts for this day
            if current_part > len(videos):
                # Move to next day
                next_day = current_day + 1
                next_day_folder = f"day{next_day}"
                
                if next_day_folder in day_folders:
                    logger.info(f"Moving to next day: {next_day_folder}")
                    self.current_state["current_day"] = next_day
                    self.current_state["current_part"] = 1
                    return self.determine_next_video()
                else:
                    # Loop back to day1
                    logger.info("All days completed, looping back to day1")
                    self.current_state["current_day"] = 1
                    self.current_state["current_part"] = 1
                    return self.determine_next_video()
            else:
                # Skip this part and try next
                self.current_state["current_part"] += 1
                return self.determine_next_video()
        
        return day_folder_name, target_video
    
    def run(self):
        """Main execution flow"""
        try:
            logger.info("=" * 50)
            logger.info("Starting Instagram Auto-Poster")
            logger.info(f"Instagram Account ID: {self.instagram_account_id}")
            logger.info(f"Current state: Day {self.current_state['current_day']}, Part {self.current_state['current_part']}")
            logger.info("=" * 50)
            
            # Check error threshold
            if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error(f"Too many consecutive errors ({self.consecutive_errors}). Stopping.")
                return False
            
            # Determine which video to post
            day_folder_name, video_info = self.determine_next_video()
            
            if not day_folder_name or not video_info:
                logger.error("Could not determine next video to post")
                self.consecutive_errors += 1
                return False
            
            day_number = int(day_folder_name.replace('day', ''))
            part_number = self.current_state["current_part"]
            
            # Get total parts in current day
            videos_in_day = self.get_videos_in_folder(day_folder_name)
            total_parts = len(videos_in_day)
            
            # Generate caption
            caption = self.generate_caption(day_number, part_number, total_parts)
            
            logger.info(f"Next video to post: {video_info['name']} from {day_folder_name}")
            logger.info(f"Part: {part_number}/{total_parts}")
            logger.info(f"Caption length: {len(caption)} characters")
            
            # Create temporary directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                download_path = Path(temp_dir) / video_info['name']
                
                # Download video
                logger.info(f"Downloading video to {download_path}...")
                if not self.download_video(video_info, download_path):
                    logger.error("Failed to download video")
                    self.consecutive_errors += 1
                    return False
                
                # Verify file exists and has content
                if not download_path.exists() or download_path.stat().st_size == 0:
                    logger.error("Downloaded file is empty or doesn't exist")
                    self.consecutive_errors += 1
                    return False
                
                file_size_mb = download_path.stat().st_size / (1024 * 1024)
                logger.info(f"Video file size: {file_size_mb:.2f} MB")
                
                # Post to Instagram
                logger.info("Posting to Instagram...")
                success = self.post_video_to_instagram(download_path, caption)
                
                if success:
                    logger.info(f"Successfully posted {video_info['name']}!")
                    
                    # Update state
                    self.current_state["current_part"] += 1
                    self.current_state["last_posted"] = datetime.datetime.now().isoformat()
                    self.current_state["total_posts"] += 1
                    self.current_state["consecutive_errors"] = 0
                    self.consecutive_errors = 0
                    
                    # Save state
                    self.save_state()
                    
                    return True
                else:
                    logger.error(f"Failed to post {video_info['name']}")
                    self.consecutive_errors += 1
                    self.current_state["consecutive_errors"] = self.consecutive_errors
                    self.current_state["error_history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "day": day_number,
                        "part": part_number,
                        "video": video_info['name'],
                        "error": "Posting failed"
                    })
                    
                    # Keep only last 10 errors
                    if len(self.current_state["error_history"]) > 10:
                        self.current_state["error_history"] = self.current_state["error_history"][-10:]
                    
                    self.save_state()
                    
                    return False
                    
        except Exception as e:
            logger.error(f"Unexpected error in run(): {e}")
            self.consecutive_errors += 1
            return False

def main():
    """Main entry point"""
    try:
        poster = InstagramAutoPoster()
        success = poster.run()
        
        if success:
            logger.info("Instagram Auto-Poster completed successfully!")
            sys.exit(0)
        else:
            logger.error("Instagram Auto-Poster failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
