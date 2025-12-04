#!/usr/bin/env python3
"""
Instagram Auto-Poster using Facebook Graph API
"""

import os
import sys
import json
import logging
import subprocess
import math
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    # Import configuration
    from config import *
    print(f"✅ Config loaded from config.py")
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

class InstagramGraphPoster:
    def __init__(self):
        self.state_file = Path("../state/posting_state.json")
        self.downloads_dir = Path("../downloads")
        self.segments_dir = Path("../segments")
        self.temp_dir = Path("../temp")
        
        # Create directories
        self.downloads_dir.mkdir(exist_ok=True)
        self.segments_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        self.state_file.parent.mkdir(exist_ok=True)
        
        # Load state
        self.state = self.load_state()
        
        # Graph API settings
        self.graph_api_url = "https://graph.facebook.com/v18.0"
        
    def load_state(self) -> Dict:
        """Load posting state from JSON file"""
        default_state = {
            "last_run_date": None,
            "current_video_index": 0,
            "current_video_id": None,
            "processed_videos": [],
            "failed_videos": [],
            "total_posts": 0,
            "consecutive_errors": 0,
            "last_error": None
        }
        
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    # Merge with default to ensure all keys exist
                    for key in default_state:
                        if key not in state:
                            state[key] = default_state[key]
                    return state
            except Exception as e:
                logger.error(f"Error loading state: {e}")
        
        return default_state
    
    def save_state(self):
        """Save posting state to JSON file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def initialize_google_drive(self, credentials_json: str):
        """Initialize Google Drive API client"""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            credentials_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            
            self.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("✅ Google Drive API initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive: {e}")
            return False
    
    def get_sorted_videos(self) -> List[Dict]:
        """Get videos sorted by name from Google Drive"""
        try:
            query = f"'{GDRIVE_FOLDER_ID}' in parents and mimeType contains 'video/'"
            
            results = self.drive_service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, mimeType, size)",
                orderBy="name"
            ).execute()
            
            videos = results.get('files', [])
            
            # Sort by name (assuming they're numbered)
            videos.sort(key=lambda x: x['name'])
            
            logger.info(f"Found {len(videos)} videos in Google Drive")
            return videos
            
        except Exception as e:
            logger.error(f"Error fetching videos: {e}")
            return []
    
    def download_video(self, video_info: Dict) -> Optional[Path]:
        """Download video from Google Drive"""
        try:
            file_id = video_info['id']
            filename = video_info['name']
            filepath = self.downloads_dir / filename
            
            logger.info(f"📥 Downloading: {filename}")
            
            request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(filepath, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.debug(f"Download progress: {int(status.progress() * 100)}%")
            
            # Verify file was downloaded
            if filepath.exists() and filepath.stat().st_size > 0:
                size_mb = filepath.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Downloaded: {filename} ({size_mb:.1f} MB)")
                return filepath
            else:
                logger.error(f"Downloaded file is empty")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading video {video_info.get('name', 'unknown')}: {e}")
            return None
    
    def get_video_duration(self, video_path: Path) -> float:
        """Get video duration using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                logger.debug(f"Video duration: {duration:.2f} seconds")
                return duration
            else:
                logger.error(f"FFprobe error: {result.stderr}")
                return 0
                
        except subprocess.TimeoutExpired:
            logger.error("FFprobe timed out")
            return 0
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return 0
    
    def calculate_segments(self, video_duration: float) -> Tuple[int, float]:
        """
        Calculate how many segments to create
        
        Returns: (num_segments, segment_duration_original)
        """
        # We want accelerated segments to be <= VIDEO_SEGMENT_MAX_DURATION
        # So original segments should be <= VIDEO_SEGMENT_MAX_DURATION * SPEED_FACTOR
        max_original_duration = VIDEO_SEGMENT_MAX_DURATION * SPEED_FACTOR
        
        # Calculate number of segments
        num_segments = math.ceil(video_duration / max_original_duration)
        
        # Ensure at least 1 segment
        num_segments = max(1, num_segments)
        
        # Calculate equal segment duration
        segment_duration_original = video_duration / num_segments
        
        # Check accelerated duration
        accelerated_duration = segment_duration_original / SPEED_FACTOR
        
        logger.info(f"Video: {video_duration:.1f}s → {num_segments} segments")
        logger.info(f"Each segment: {segment_duration_original:.1f}s original → {accelerated_duration:.1f}s at {SPEED_FACTOR}x")
        
        return num_segments, segment_duration_original
    
    def split_and_accelerate_video(self, video_path: Path, num_segments: int, 
                                  segment_duration_original: float) -> List[Path]:
        """
        Split video into equal segments and accelerate to 1.25x
        Returns list of segment file paths
        """
        segments = []
        video_name = video_path.stem
        
        try:
            for i in range(num_segments):
                start_time = i * segment_duration_original
                
                # Output filename
                segment_filename = f"{video_name}_part_{i+1}.mp4"
                segment_path = self.segments_dir / segment_filename
                
                logger.info(f"Creating Part {i+1}/{num_segments}: {start_time:.1f}s to {start_time + segment_duration_original:.1f}s")
                
                # FFmpeg command to extract segment and speed up
                cmd = [
                    'ffmpeg', '-y',
                    '-ss', str(start_time),
                    '-i', str(video_path),
                    '-t', str(segment_duration_original),
                    '-filter:v', f'setpts={1/SPEED_FACTOR}*PTS',
                    '-filter:a', f'atempo={SPEED_FACTOR}',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    str(segment_path)
                ]
                
                # Run ffmpeg
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    # Verify segment duration
                    segment_duration = self.get_video_duration(segment_path)
                    if segment_duration > 0 and segment_duration <= VIDEO_SEGMENT_MAX_DURATION:
                        segments.append(segment_path)
                        logger.info(f"✓ Created Part {i+1}: {segment_duration:.1f}s")
                    else:
                        logger.error(f"Segment {i+1} duration invalid: {segment_duration:.1f}s")
                        if segment_path.exists():
                            segment_path.unlink()
                else:
                    logger.error(f"FFmpeg error for Part {i+1}: {result.stderr[:200]}")
            
            return segments
            
        except Exception as e:
            logger.error(f"Error splitting video: {e}")
            # Clean up any created segments
            for segment in segments:
                if segment.exists():
                    segment.unlink()
            return []
    
    def get_instagram_account_id(self) -> Optional[str]:
        """Get Instagram Business Account ID from Facebook Graph API"""
        try:
            # First, get user's pages
            pages_url = f"{self.graph_api_url}/me/accounts"
            params = {
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'fields': 'id,name,access_token,instagram_business_account'
            }
            
            logger.info(f"Getting pages for user {FACEBOOK_USER_ID}...")
            response = requests.get(pages_url, params=params)
            
            if response.status_code == 200:
                pages_data = response.json()
                pages = pages_data.get('data', [])
                
                logger.info(f"Found {len(pages)} pages")
                
                for page in pages:
                    page_name = page.get('name', 'Unknown')
                    page_id = page.get('id')
                    instagram_account = page.get('instagram_business_account')
                    
                    logger.info(f"Page: {page_name} (ID: {page_id})")
                    
                    if instagram_account:
                        instagram_id = instagram_account.get('id')
                        logger.info(f"✅ Found Instagram Business Account: {instagram_id}")
                        return instagram_id
                
                logger.warning("No Instagram Business Account found connected to pages")
                
                # Try to get Instagram account directly
                logger.info("Trying to get Instagram account directly...")
                instagram_url = f"{self.graph_api_url}/{FACEBOOK_USER_ID}/accounts"
                params = {
                    'access_token': FACEBOOK_ACCESS_TOKEN,
                    'fields': 'instagram_business_account'
                }
                
                response = requests.get(instagram_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if 'instagram_business_account' in data:
                        instagram_id = data['instagram_business_account']['id']
                        logger.info(f"✅ Found Instagram Business Account: {instagram_id}")
                        return instagram_id
                
            else:
                logger.error(f"Failed to get pages: {response.status_code} - {response.text}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting Instagram account ID: {e}")
            return None
    
    def post_to_instagram_graph_api(self, video_path: Path, caption: str) -> bool:
        """Post video to Instagram using Facebook Graph API"""
        try:
            # Get Instagram Business Account ID
            instagram_id = self.get_instagram_account_id()
            if not instagram_id:
                logger.error("Could not get Instagram Business Account ID")
                return False
            
            logger.info(f"Posting to Instagram Account ID: {instagram_id}")
            
            # Step 1: Create media container
            logger.info("Step 1: Creating media container...")
            
            # Check video size (Instagram limit: 100MB for feed, 250MB for Reels)
            video_size_mb = video_path.stat().st_size / (1024 * 1024)
            logger.info(f"Video size: {video_size_mb:.1f} MB")
            
            if video_size_mb > 100:
                logger.warning(f"Video size ({video_size_mb:.1f}MB) exceeds 100MB limit for feed")
                # We'll try anyway, Instagram might accept it for Reels
            
            # For Reels, use media_type=REELS
            # For feed video, use media_type=VIDEO
            
            # Upload video directly
            upload_url = f"{self.graph_api_url}/{instagram_id}/media"
            
            logger.info(f"Uploading to: {upload_url}")
            
            with open(video_path, 'rb') as video_file:
                files = {
                    'media_type': (None, 'REELS'),
                    'video': (video_path.name, video_file, 'video/mp4'),
                    'caption': (None, caption),
                    'access_token': (None, FACEBOOK_ACCESS_TOKEN)
                }
                
                response = requests.post(upload_url, files=files)
                
                if response.status_code == 200:
                    result = response.json()
                    creation_id = result.get('id')
                    
                    if creation_id:
                        logger.info(f"✅ Media uploaded successfully! Creation ID: {creation_id}")
                        
                        # Step 2: Publish the media
                        logger.info("Step 2: Publishing media...")
                        
                        publish_url = f"{self.graph_api_url}/{instagram_id}/media_publish"
                        publish_data = {
                            'creation_id': creation_id,
                            'access_token': FACEBOOK_ACCESS_TOKEN
                        }
                        
                        # Add delay before publishing
                        time.sleep(2)
                        
                        publish_response = requests.post(publish_url, data=publish_data)
                        
                        if publish_response.status_code == 200:
                            publish_result = publish_response.json()
                            media_id = publish_result.get('id')
                            logger.info(f"✅ Published successfully! Media ID: {media_id}")
                            return True
                        else:
                            logger.error(f"Publish failed: {publish_response.status_code} - {publish_response.text}")
                            return False
                    else:
                        logger.error(f"No creation ID in response: {result}")
                        return False
                else:
                    logger.error(f"Upload failed: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error posting via Graph API: {e}")
            return False
    
    def create_caption(self, video_name: str, part_number: int, total_parts: int) -> str:
        """Create Instagram caption with part information"""
        hashtags = "#autopost #dailycontent #viral #trending #reels #instagood #viralvideo #fyp #fun #entertainment"
        
        caption = f"""🎬 Part {part_number}/{total_parts} - {video_name}

🔁 Speed: {SPEED_FACTOR}x
⚡ Posted automatically via Facebook Graph API
📅 {datetime.now().strftime('%B %d, %Y')}

{hashtags}

#Part{part_number} #AutoPost #Tech #AI #GitHubActions"""
        
        return caption
    
    def cleanup_files(self, *paths):
        """Clean up temporary files"""
        for path in paths:
            if path and Path(path).exists():
                try:
                    Path(path).unlink()
                    logger.debug(f"Cleaned up: {path}")
                except Exception as e:
                    logger.debug(f"Error cleaning up {path}: {e}")
    
    def should_run_today(self) -> bool:
        """Check if we should run today based on last run date"""
        if not POST_DAILY:
            return True
        
        last_run = self.state.get('last_run_date')
        if not last_run:
            return True
        
        try:
            last_run_date = datetime.fromisoformat(last_run)
            today = datetime.now().date()
            
            if last_run_date.date() >= today:
                logger.info(f"Already ran today ({last_run_date.date()}), skipping")
                return False
            else:
                return True
        except Exception as e:
            logger.warning(f"Error checking last run date: {e}")
            return True
    
    def run(self, credentials_json: str):
        """Main execution method"""
        logger.info("=" * 60)
        logger.info("INSTAGRAM AUTO-POSTER (Facebook Graph API)")
        logger.info("=" * 60)
        
        # Check if we should run today
        if not self.should_run_today():
            logger.info("Daily posting already done, exiting")
            return
        
        # Check for too many consecutive errors
        if self.state['consecutive_errors'] >= MAX_ERRORS_BEFORE_STOP:
            logger.error(f"Too many consecutive errors ({self.state['consecutive_errors']}), stopping")
            return
        
        # Initialize Google Drive
        if not self.initialize_google_drive(credentials_json):
            logger.error("Failed to initialize Google Drive, exiting")
            return
        
        # Get videos from Drive
        videos = self.get_sorted_videos()
        if not videos:
            logger.warning("No videos found in Google Drive")
            return
        
        # Determine which video to process
        current_index = self.state['current_video_index']
        
        # Skip already processed videos
        processed_ids = {v['id'] for v in self.state['processed_videos']}
        while current_index < len(videos) and videos[current_index]['id'] in processed_ids:
            current_index += 1
        
        # Check if we've processed all videos
        if current_index >= len(videos):
            logger.info("All videos have been processed, resetting index")
            current_index = 0
            self.state['current_video_index'] = 0
            self.state['processed_videos'] = []  # Reset for new cycle
            self.save_state()
        
        # Get current video
        current_video = videos[current_index]
        logger.info(f"Processing video {current_index + 1}/{len(videos)}: {current_video['name']}")
        
        # Download video
        video_path = self.download_video(current_video)
        if not video_path:
            logger.error("Failed to download video")
            self.state['consecutive_errors'] += 1
            self.save_state()
            return
        
        # Get video duration
        video_duration = self.get_video_duration(video_path)
        if video_duration <= 0:
            self.cleanup_files(video_path)
            logger.error("Invalid video duration")
            self.state['consecutive_errors'] += 1
            self.save_state()
            return
        
        # Calculate segments
        num_segments, segment_duration_original = self.calculate_segments(video_duration)
        
        # Split and accelerate video
        segments = self.split_and_accelerate_video(video_path, num_segments, segment_duration_original)
        
        # Clean up downloaded video
        self.cleanup_files(video_path)
        
        if not segments:
            logger.error("Failed to create video segments")
            self.state['consecutive_errors'] += 1
            self.save_state()
            return
        
        # Post first segment to Instagram
        if segments:
            segment = segments[0]
            part_number = 1
            
            # Create caption
            caption = self.create_caption(current_video['name'], part_number, num_segments)
            
            logger.info(f"📤 Posting Part {part_number}/{num_segments}")
            logger.info(f"   Caption: {caption[:50]}...")
            
            # Post to Instagram using Graph API
            success = self.post_to_instagram_graph_api(segment, caption)
            
            if success:
                logger.info(f"✅ Successfully posted Part {part_number}")
                
                # Update state
                self.state['last_run_date'] = datetime.now().isoformat()
                self.state['current_video_index'] = current_index + 1
                self.state['processed_videos'].append({
                    'id': current_video['id'],
                    'name': current_video['name'],
                    'date': datetime.now().isoformat()
                })
                self.state['total_posts'] += 1
                self.state['consecutive_errors'] = 0
                
                # Save state
                self.save_state()
                
                logger.info(f"\n📊 Next: Video {self.state['current_video_index'] + 1} of {len(videos)}")
                
            else:
                logger.error("❌ Failed to post to Instagram")
                self.state['consecutive_errors'] += 1
                self.save_state()
            
            # Clean up segment
            self.cleanup_files(segment)
        
        logger.info("=" * 60)
        logger.info("Process completed!")
        logger.info("=" * 60)

def main():
    """Main entry point"""
    try:
        # Check for required tools
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("FFmpeg/FFprobe not found. Please install ffmpeg.")
            logger.error("Ubuntu/Debian: sudo apt install ffmpeg")
            logger.error("macOS: brew install ffmpeg")
            sys.exit(1)
        
        # Load Google Drive credentials from environment
        credentials_json = os.getenv("GDRIVE_CREDENTIALS")
        if not credentials_json:
            logger.error("Google Drive credentials not found")
            sys.exit(1)
        
        # Create and run poster
        poster = InstagramGraphPoster()
        poster.run(credentials_json)
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
