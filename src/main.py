#!/usr/bin/env python3
"""
Instagram Auto-Posting System
Posts videos from Google Drive to Instagram Reels via Facebook Graph API
"""

import os
import sys
import json
import logging
import argparse
import tempfile
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

# Third-party imports
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import requests
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install required packages: pip install -r requirements.txt")
    sys.exit(1)

# Import configuration
try:
    import config
except ImportError:
    print("Error: config.py not found. Ensure GitHub Secrets are properly set.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_poster.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class GoogleDriveClient:
    """Handles Google Drive operations"""
    
    def __init__(self, credentials_json: str):
        self.credentials_json = credentials_json
        self.service = None
        self._authenticate()
        
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        try:
            # Parse credentials from JSON string
            creds_dict = json.loads(self.credentials_json)
            
            # Create credentials object
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            
            # Build the service
            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("✅ Google Drive authentication successful")
            
        except Exception as e:
            logger.error(f"❌ Google Drive authentication failed: {e}")
            raise
            
    def list_folders(self, parent_id: str) -> List[Dict]:
        """List all folders in a parent folder"""
        try:
            query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder'"
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            # Sort folders by name (day1, day2, etc.)
            folders.sort(key=lambda x: x['name'])
            logger.info(f"📁 Found {len(folders)} folders")
            return folders
            
        except Exception as e:
            logger.error(f"❌ Failed to list folders: {e}")
            return []
            
    def list_files(self, folder_id: str) -> List[Dict]:
        """List all files in a folder"""
        try:
            query = f"'{folder_id}' in parents and mimeType contains 'video/'"
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, size, mimeType, createdTime)"
            ).execute()
            
            files = results.get('files', [])
            # Sort files by name (part1.mp4, part2.mp4, etc.)
            files.sort(key=lambda x: x['name'])
            logger.info(f"🎬 Found {len(files)} video files")
            return files
            
        except Exception as e:
            logger.error(f"❌ Failed to list files: {e}")
            return []
            
    def download_file(self, file_id: str, file_path: str) -> bool:
        """Download a file from Google Drive"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            with open(file_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.info(f"⬇️ Download progress: {int(status.progress() * 100)}%")
                        
            logger.info(f"✅ Downloaded file to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download file: {e}")
            return False


class InstagramPoster:
    """Handles Instagram posting via Facebook Graph API"""
    
    def __init__(self, access_token: str, user_id: str):
        self.access_token = access_token
        self.user_id = user_id
        self.base_url = "https://graph.facebook.com/v18.0"
        
    def create_media_container(self, video_path: str, caption: str) -> Optional[str]:
        """Create a media container for the video"""
        try:
            # First, upload the video
            with open(video_path, 'rb') as video_file:
                files = {'video': video_file}
                data = {
                    'access_token': self.access_token,
                    'caption': caption,
                    'media_type': 'REELS'
                }
                
                # Create container
                response = requests.post(
                    f"{self.base_url}/{self.user_id}/media",
                    data=data,
                    files=files
                )
                
                if response.status_code == 200:
                    container_id = response.json().get('id')
                    logger.info(f"📦 Created media container: {container_id}")
                    return container_id
                else:
                    logger.error(f"❌ Failed to create container: {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Error creating media container: {e}")
            return None
            
    def publish_media(self, container_id: str) -> bool:
        """Publish the media container"""
        try:
            # Check container status
            status_url = f"{self.base_url}/{container_id}"
            for _ in range(30):  # Wait up to 5 minutes
                status_response = requests.get(
                    status_url,
                    params={'access_token': self.access_token,
                           'fields': 'status_code,status'}
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    status = status_data.get('status_code', '')
                    
                    if status == 'FINISHED':
                        # Publish the container
                        publish_url = f"{self.base_url}/{self.user_id}/media_publish"
                        publish_data = {
                            'creation_id': container_id,
                            'access_token': self.access_token
                        }
                        
                        publish_response = requests.post(publish_url, data=publish_data)
                        if publish_response.status_code == 200:
                            logger.info("✅ Video published successfully!")
                            return True
                        else:
                            logger.error(f"❌ Failed to publish: {publish_response.text}")
                            return False
                            
                    elif status == 'ERROR':
                        logger.error(f"❌ Container error: {status_data}")
                        return False
                        
                    # Wait before checking again
                    import time
                    time.sleep(10)
                else:
                    logger.error(f"❌ Failed to check container status: {status_response.text}")
                    return False
                    
            logger.error("❌ Timeout waiting for container to be ready")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error publishing media: {e}")
            return False
            
    def post_video(self, video_path: str, caption: str) -> bool:
        """Complete video posting flow"""
        logger.info("🚀 Starting Instagram posting process...")
        
        # Create media container
        container_id = self.create_media_container(video_path, caption)
        if not container_id:
            return False
            
        # Publish media
        return self.publish_media(container_id)


class StateManager:
    """Manages posting state persistence"""
    
    def __init__(self, state_file: str = "state/posting_state.json"):
        self.state_file = state_file
        self.state = self._load_state()
        
    def _load_state(self) -> Dict:
        """Load state from JSON file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.info(f"📊 Loaded state: {state}")
                    return state
            else:
                # Initial state
                initial_state = {
                    "current_day": "day1",
                    "current_part": 1,
                    "total_parts_current_day": 0,
                    "last_posted": None,
                    "consecutive_errors": 0,
                    "total_posts": 0,
                    "completed_days": [],
                    "posting_history": []
                }
                logger.info("📊 Initialized new state")
                return initial_state
                
        except Exception as e:
            logger.error(f"❌ Failed to load state: {e}")
            return {
                "current_day": "day1",
                "current_part": 1,
                "last_posted": None,
                "consecutive_errors": 0
            }
            
    def save_state(self):
        """Save state to JSON file"""
        try:
            # Ensure state directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.info(f"💾 State saved: {self.state}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save state: {e}")
            
    def update_post_success(self, day: str, part: int, total_parts: int, video_name: str):
        """Update state after successful post"""
        self.state["current_day"] = day
        self.state["current_part"] = part + 1  # Next part
        self.state["total_parts_current_day"] = total_parts
        self.state["last_posted"] = datetime.now().isoformat()
        self.state["consecutive_errors"] = 0
        self.state["total_posts"] = self.state.get("total_posts", 0) + 1
        
        # Add to history
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "day": day,
            "part": part,
            "video": video_name,
            "status": "success"
        }
        self.state.setdefault("posting_history", []).append(history_entry)
        
        # Keep only last 100 history entries
        if len(self.state["posting_history"]) > 100:
            self.state["posting_history"] = self.state["posting_history"][-100:]
            
        # If we've posted all parts in this day, move to next day
        if part >= total_parts:
            self._move_to_next_day(day)
            
        self.save_state()
        
    def _move_to_next_day(self, current_day: str):
        """Move to the next day folder"""
        # Extract day number
        try:
            day_num = int(current_day.replace("day", ""))
            next_day = f"day{day_num + 1}"
            self.state["current_day"] = next_day
            self.state["current_part"] = 1
            
            # Add current day to completed days
            if current_day not in self.state.get("completed_days", []):
                self.state.setdefault("completed_days", []).append(current_day)
                
            logger.info(f"📅 Moving to next day: {next_day}")
            
        except ValueError:
            logger.error(f"❌ Could not parse day number from {current_day}")
            
    def update_post_error(self, error_message: str):
        """Update state after posting error"""
        self.state["consecutive_errors"] = self.state.get("consecutive_errors", 0) + 1
        self.state.setdefault("error_history", []).append({
            "timestamp": datetime.now().isoformat(),
            "error": error_message
        })
        
        # Keep only last 50 error entries
        if len(self.state.get("error_history", [])) > 50:
            self.state["error_history"] = self.state["error_history"][-50:]
            
        self.save_state()
        
    def should_continue(self) -> bool:
        """Check if we should continue posting based on error count"""
        max_errors = getattr(config, 'MAX_CONSECUTIVE_ERRORS', 5)
        return self.state.get("consecutive_errors", 0) < max_errors


class InstagramAutoPoster:
    """Main class orchestrating the auto-posting system"""
    
    def __init__(self):
        # Initialize components
        self.state_manager = StateManager()
        self.drive_client = GoogleDriveClient(config.GDRIVE_CREDENTIALS)
        self.instagram_poster = InstagramPoster(
            config.FACEBOOK_ACCESS_TOKEN,
            config.FACEBOOK_USER_ID
        )
        
    def find_next_video(self, force_day: str = None, force_part: int = None) -> Tuple[Optional[Dict], Optional[Dict], int]:
        """Find the next video to post"""
        # Use forced values or state values
        target_day = force_day or self.state_manager.state["current_day"]
        target_part = force_part or self.state_manager.state["current_part"]
        
        logger.info(f"🔍 Looking for: {target_day}/part{target_part}.mp4")
        
        # List all folders
        folders = self.drive_client.list_folders(config.GDRIVE_FOLDER_ID)
        if not folders:
            logger.error("❌ No folders found in Google Drive")
            return None, None, 0
            
        # Find target folder
        target_folder = None
        for folder in folders:
            if folder['name'].lower() == target_day.lower():
                target_folder = folder
                break
                
        if not target_folder:
            logger.error(f"❌ Folder '{target_day}' not found")
            # Try to find the next available folder
            for folder in folders:
                if folder['name'] not in self.state_manager.state.get("completed_days", []):
                    target_folder = folder
                    logger.info(f"🔄 Falling back to folder: {folder['name']}")
                    break
                    
            if not target_folder:
                logger.error("❌ No more folders to process")
                return None, None, 0
                
        # List files in the folder
        files = self.drive_client.list_files(target_folder['id'])
        if not files:
            logger.error(f"❌ No video files found in {target_folder['name']}")
            return None, None, 0
            
        # Sort files by name and find target part
        files.sort(key=lambda x: x['name'])
        total_parts = len(files)
        
        # Find the specific part
        target_video = None
        for file in files:
            # Extract part number from filename
            try:
                # Handle various naming patterns: part1.mp4, part1_video.mp4, etc.
                filename = file['name'].lower()
                if 'part' in filename:
                    # Extract number after 'part'
                    import re
                    match = re.search(r'part(\d+)', filename)
                    if match:
                        part_num = int(match.group(1))
                        if part_num == target_part:
                            target_video = file
                            break
            except (ValueError, AttributeError):
                continue
                
        # If target part not found, try first file
        if not target_video and files:
            target_video = files[0]
            logger.warning(f"⚠️ Part {target_part} not found, using first video")
            
        return target_folder, target_video, total_parts
        
    def generate_caption(self, day: str, part: int, total_parts: int) -> str:
        """Generate caption for the post"""
        # Extract day number
        day_num = day.replace("day", "").replace("Day", "").replace("DAY", "")
        
        # Current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Use template from config
        caption_template = getattr(config, 'CAPTION_TEMPLATE', 
            """Day {day_number} - Part {part_number}/{total_parts}

📅 Posted automatically on {date}
⚡ Powered by GitHub Actions & Facebook Graph API

#Day{day_number} #Part{part_number} #InstagramReels #AutoPost #Tech #AI #GitHubActions #Coding #Automation""")
        
        caption = caption_template.format(
            day_number=day_num,
            part_number=part,
            total_parts=total_parts,
            date=current_date
        )
        
        return caption
        
    def post_video(self, folder: Dict, video: Dict, part_number: int, total_parts: int) -> bool:
        """Download and post a video"""
        try:
            logger.info(f"🎥 Processing: {folder['name']}/{video['name']}")
            
            # Create temp file for video
            temp_dir = tempfile.gettempdir()
            temp_video_path = os.path.join(temp_dir, "instagram_video.mp4")
            
            # Download video
            logger.info(f"⬇️ Downloading video...")
            if not self.drive_client.download_file(video['id'], temp_video_path):
                raise Exception("Failed to download video")
                
            # Generate caption
            caption = self.generate_caption(folder['name'], part_number, total_parts)
            logger.info(f"📝 Caption:\n{caption}")
            
            # Post to Instagram
            logger.info("📤 Posting to Instagram Reels...")
            success = self.instagram_poster.post_video(temp_video_path, caption)
            
            # Clean up temp file
            try:
                os.remove(temp_video_path)
            except:
                pass
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Error in post_video: {e}")
            return False
            
    def run(self, force_day: str = None, force_part: int = None):
        """Main execution flow"""
        logger.info("🚀 Starting Instagram Auto-Poster")
        
        # Check if we should continue based on error count
        if not self.state_manager.should_continue():
            logger.error("🚫 Too many consecutive errors. Stopping.")
            return False
            
        try:
            # Find next video to post
            folder, video, total_parts = self.find_next_video(force_day, force_part)
            if not folder or not video:
                logger.error("❌ Could not find video to post")
                self.state_manager.update_post_error("No video found")
                return False
                
            # Determine part number
            current_part = force_part or self.state_manager.state["current_part"]
            
            # Post the video
            success = self.post_video(folder, video, current_part, total_parts)
            
            if success:
                logger.info("✅ Post successful!")
                self.state_manager.update_post_success(
                    folder['name'],
                    current_part,
                    total_parts,
                    video['name']
                )
                return True
            else:
                logger.error("❌ Post failed")
                self.state_manager.update_post_error("Instagram posting failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            self.state_manager.update_post_error(str(e))
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Instagram Auto Poster')
    parser.add_argument('--force-day', help='Force specific day folder', default=None)
    parser.add_argument('--force-part', type=int, help='Force specific part number', default=None)
    
    args = parser.parse_args()
    
    # Create auto-poster instance
    poster = InstagramAutoPoster()
    
    # Run the poster
    success = poster.run(args.force_day, args.force_part)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
