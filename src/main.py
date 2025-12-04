#!/usr/bin/env python3
"""
Instagram Auto-Poster
Automatically posts videos from Google Drive to Instagram
Features:
- 1 video per day
- 1.25x speed acceleration
- Equal splitting under 2:50 minutes
- Automatic error handling and skipping
- Part numbering in descriptions
"""

import os
import sys
import json
import time
import logging
import subprocess
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Third-party imports
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired, ChallengeRequired
except ImportError as e:
    print(f"Missing dependencies: {e}")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)

# Import configuration
try:
    from config import *
except ImportError:
    print("Warning: config.py not found. Using environment variables.")
    # Default values that can be overridden by environment
    INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
    INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")
    GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")
    VIDEO_SEGMENT_MAX_DURATION = int(os.getenv("VIDEO_SEGMENT_MAX_DURATION", "170"))
    SPEED_FACTOR = float(os.getenv("SPEED_FACTOR", "1.25"))
    SKIP_PROBLEMATIC_VIDEOS = os.getenv("SKIP_PROBLEMATIC_VIDEOS", "True").lower() == "true"

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL) if 'LOG_LEVEL' in globals() else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE if 'LOG_FILE' in globals() else 'instagram_poster.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class InstagramAutoPoster:
    """Main class for Instagram auto-posting functionality"""
    
    def __init__(self):
        """Initialize the auto-poster"""
        self.state_file = Path("state/posting_state.json")
        self.downloads_dir = Path("downloads")
        self.segments_dir = Path("segments")
        self.temp_dir = Path("temp")
        
        # Create directories
        self.downloads_dir.mkdir(exist_ok=True)
        self.segments_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        self.state_file.parent.mkdir(exist_ok=True)
        
        # Load state
        self.state = self.load_state()
        
        # Initialize clients
        self.drive_service = None
        self.instagram_client = None
        
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
        """Save current state to JSON file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def initialize_google_drive(self, credentials_json: str) -> bool:
        """Initialize Google Drive API client"""
        try:
            if isinstance(credentials_json, str):
                credentials_info = json.loads(credentials_json)
            else:
                credentials_info = credentials_json
                
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            
            self.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive API initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive: {e}")
            return False
    
    def get_videos_from_drive(self) -> List[Dict]:
        """Get list of videos from Google Drive folder, sorted by name"""
        try:
            if not self.drive_service:
                raise ValueError("Google Drive service not initialized")
            
            # Query for video files
            query = f"'{GDRIVE_FOLDER_ID}' in parents and mimeType contains 'video/'"
            
            results = self.drive_service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, mimeType, size, createdTime)",
                orderBy="name"  # Sort by name (alphabetical/numerical)
            ).execute()
            
            videos = results.get('files', [])
            
            # Filter and sort
            videos = [v for v in videos if self._is_video_file(v['name'])]
            videos.sort(key=lambda x: x['name'])
            
            logger.info(f"Found {len(videos)} videos in Google Drive")
            return videos
            
        except Exception as e:
            logger.error(f"Error fetching videos from Drive: {e}")
            return []
    
    def _is_video_file(self, filename: str) -> bool:
        """Check if file is a video based on extension"""
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
        return any(filename.lower().endswith(ext) for ext in video_extensions)
    
    def download_video(self, video_info: Dict) -> Optional[Path]:
        """Download video from Google Drive"""
        try:
            file_id = video_info['id']
            filename = video_info['name']
            filepath = self.downloads_dir / filename
            
            logger.info(f"Downloading: {filename}")
            
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
                logger.info(f"Downloaded successfully: {filename} ({filepath.stat().st_size / (1024*1024):.1f} MB)")
                return filepath
            else:
                logger.error(f"Downloaded file is empty or doesn't exist")
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
        Calculate how many segments to create and their duration
        
        Returns: (num_segments, segment_duration_original)
        """
        # Adjust for speed factor
        # We want accelerated segments to be <= VIDEO_SEGMENT_MAX_DURATION
        # So original segments should be <= VIDEO_SEGMENT_MAX_DURATION * SPEED_FACTOR
        max_original_duration = VIDEO_SEGMENT_MAX_DURATION * SPEED_FACTOR
        
        # Calculate number of segments needed
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
                    '-filter:a', f'atempo={SPEED_FACTOR}' if SPEED_FACTOR != 1.0 else 'anull',
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
    
    def initialize_instagram(self) -> bool:
        """Initialize Instagram client"""
        try:
            self.instagram_client = Client()
            
            # Set up proxy if needed (for GitHub Actions)
            # self.instagram_client.set_proxy("http://proxy:port")
            
            # Login to Instagram
            logger.info("Logging into Instagram...")
            self.instagram_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            
            # Verify login
            user_id = self.instagram_client.user_id
            if user_id:
                logger.info(f"Successfully logged in as {INSTAGRAM_USERNAME} (ID: {user_id})")
                return True
            else:
                logger.error("Instagram login failed: No user ID returned")
                return False
                
        except LoginRequired as e:
            logger.error(f"Instagram login required: {e}")
            return False
        except ChallengeRequired as e:
            logger.error(f"Instagram challenge required: {e}")
            return False
        except Exception as e:
            logger.error(f"Instagram initialization error: {e}")
            return False
    
    def create_caption(self, video_name: str, part_number: int, total_parts: int) -> str:
        """Create Instagram caption with part information"""
        hashtags = "#autopost #dailycontent #viral #trending #reels #instagood #viralvideo #fyp #fun #entertainment"
        
        caption = f"""🎬 Part {part_number}/{total_parts} - {video_name}

🔁 Speed: {SPEED_FACTOR}x
📅 Posted automatically on {datetime.now().strftime('%B %d, %Y')}

{hashtags}

#Part{part_number} #AutoPost #Tech #AI #GitHubActions"""
        
        return caption
    
    def post_to_instagram(self, video_path: Path, caption: str) -> bool:
        """Post video to Instagram"""
        try:
            if not self.instagram_client:
                logger.error("Instagram client not initialized")
                return False
            
            # Check video size
            video_size_mb = video_path.stat().st_size / (1024 * 1024)
            if video_size_mb > INSTAGRAM_MAX_VIDEO_SIZE_MB:
                logger.error(f"Video too large: {video_size_mb:.1f}MB > {INSTAGRAM_MAX_VIDEO_SIZE_MB}MB limit")
                return False
            
            # Upload video
            logger.info(f"Uploading to Instagram: {video_path.name}")
            logger.debug(f"Video size: {video_size_mb:.1f}MB, Caption length: {len(caption)} chars")
            
            media = self.instagram_client.clip_upload(
                str(video_path),
                caption=caption
            )
            
            if media and hasattr(media, 'id'):
                logger.info(f"✓ Successfully posted! Media ID: {media.id}")
                return True
            else:
                logger.error("Upload returned no media ID")
                return False
                
        except Exception as e:
            logger.error(f"Error posting to Instagram: {e}")
            return False
    
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
    
    def mark_as_processed(self, video_info: Dict, success: bool):
        """Update state after processing a video"""
        video_id = video_info['id']
        
        if success:
            self.state['processed_videos'].append({
                'id': video_id,
                'name': video_info['name'],
                'date': datetime.now().isoformat(),
                'type': 'success'
            })
            self.state['consecutive_errors'] = 0
            self.state['total_posts'] += 1
        else:
            self.state['failed_videos'].append({
                'id': video_id,
                'name': video_info['name'],
                'date': datetime.now().isoformat(),
                'type': 'failed'
            })
            self.state['consecutive_errors'] += 1
            self.state['last_error'] = datetime.now().isoformat()
        
        self.state['last_run_date'] = datetime.now().isoformat()
        self.save_state()
    
    def skip_problematic_video(self, video_info: Dict, reason: str):
        """Skip a problematic video and update state"""
        logger.warning(f"Skipping video '{video_info['name']}': {reason}")
        
        self.state['failed_videos'].append({
            'id': video_info['id'],
            'name': video_info['name'],
            'date': datetime.now().isoformat(),
            'reason': reason,
            'type': 'skipped'
        })
        
        self.state['consecutive_errors'] += 1
        self.save_state()
    
    def run(self, credentials_json: str):
        """Main execution method"""
        logger.info("=" * 60)
        logger.info("INSTAGRAM AUTO-POSTER - STARTING")
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
        videos = self.get_videos_from_drive()
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
            self.skip_problematic_video(current_video, "Download failed")
            self.state['current_video_index'] = current_index + 1
            self.save_state()
            return
        
        # Get video duration
        video_duration = self.get_video_duration(video_path)
        if video_duration <= 0:
            self.cleanup_files(video_path)
            self.skip_problematic_video(current_video, "Invalid duration")
            self.state['current_video_index'] = current_index + 1
            self.save_state()
            return
        
        # Check if video is too long
        if video_duration > MAX_ORIGINAL_VIDEO_LENGTH:
            logger.warning(f"Video too long ({video_duration:.0f}s > {MAX_ORIGINAL_VIDEO_LENGTH}s), skipping")
            self.cleanup_files(video_path)
            self.skip_problematic_video(current_video, "Too long")
            self.state['current_video_index'] = current_index + 1
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
            self.skip_problematic_video(current_video, "Segment creation failed")
            self.state['current_video_index'] = current_index + 1
            self.save_state()
            return
        
        # Initialize Instagram
        if not self.initialize_instagram():
            logger.error("Failed to initialize Instagram")
            # Clean up segments
            for segment in segments:
                self.cleanup_files(segment)
            return
        
        # Post segments to Instagram
        success_count = 0
        for i, segment_path in enumerate(segments):
            part_number = i + 1
            
            # Create caption
            caption = self.create_caption(current_video['name'], part_number, num_segments)
            
            # Post to Instagram
            if self.post_to_instagram(segment_path, caption):
                success_count += 1
                logger.info(f"Successfully posted Part {part_number}/{num_segments}")
                
                # Add delay between posts if posting multiple segments
                if i < len(segments) - 1 and DELAY_BETWEEN_POSTS > 0:
                    logger.info(f"Waiting {DELAY_BETWEEN_POSTS} seconds before next post...")
                    time.sleep(DELAY_BETWEEN_POSTS)
            else:
                logger.error(f"Failed to post Part {part_number}")
                
                # If SKIP_PROBLEMATIC_VIDEOS is True, continue with next segment
                if not SKIP_PROBLEMATIC_VIDEOS:
                    break
            
            # Clean up segment
            self.cleanup_files(segment_path)
        
        # Update state
        if success_count > 0:
            self.mark_as_processed(current_video, success=True)
            self.state['current_video_index'] = current_index + 1
            logger.info(f"Successfully processed {success_count}/{len(segments)} segments")
        else:
            self.mark_as_processed(current_video, success=False)
            self.state['current_video_index'] = current_index + 1
            logger.error("No segments were posted successfully")
        
        # Logout from Instagram
        try:
            if self.instagram_client:
                self.instagram_client.logout()
                logger.info("Logged out from Instagram")
        except Exception as e:
            logger.debug(f"Error logging out: {e}")
        
        logger.info("=" * 60)
        logger.info("PROCESS COMPLETED")
        logger.info("=" * 60)
        
        # Print summary
        logger.info(f"Total processed videos: {len(self.state['processed_videos'])}")
        logger.info(f"Total failed videos: {len(self.state['failed_videos'])}")
        logger.info(f"Next video index: {self.state['current_video_index']}")

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
        
        # Load Google Drive credentials from environment variable
        credentials_json = os.getenv("GDRIVE_CREDENTIALS")
        if not credentials_json:
            # Try to load from file
            creds_file = Path("gdrive_credentials.json")
            if creds_file.exists():
                with open(creds_file, 'r') as f:
                    credentials_json = f.read()
            else:
                logger.error("Google Drive credentials not found in environment or file")
                sys.exit(1)
        
        # Create and run poster
        poster = InstagramAutoPoster()
        poster.run(credentials_json)
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()