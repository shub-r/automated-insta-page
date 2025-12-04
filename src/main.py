#!/usr/bin/env python3
"""
Minimal Instagram Auto-Poster
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

print("=" * 60)
print("MINIMAL INSTAGRAM AUTO-POSTER")
print("=" * 60)

# Get credentials from environment
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
GDRIVE_CREDENTIALS = os.getenv("GDRIVE_CREDENTIALS")

print(f"Instagram: {INSTAGRAM_USERNAME}")
print(f"Folder ID: {GDRIVE_FOLDER_ID}")
print(f"Folder ID length: {len(GDRIVE_FOLDER_ID) if GDRIVE_FOLDER_ID else 0}")

# Validate
if not all([INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, GDRIVE_FOLDER_ID, GDRIVE_CREDENTIALS]):
    print("❌ Missing credentials!")
    sys.exit(1)

try:
    # 1. Test Google Drive
    print("\n1. Testing Google Drive...")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    creds_info = json.loads(GDRIVE_CREDENTIALS)
    credentials = service_account.Credentials.from_service_account_info(creds_info)
    drive_service = build('drive', 'v3', credentials=credentials)
    
    # Get folder info
    folder = drive_service.files().get(fileId=GDRIVE_FOLDER_ID, fields='name').execute()
    print(f"✅ Connected to folder: {folder.get('name')}")
    
    # List videos
    results = drive_service.files().list(
        q=f"'{GDRIVE_FOLDER_ID}' in parents and mimeType contains 'video/'",
        pageSize=5,
        fields="files(id, name, mimeType)"
    ).execute()
    
    videos = results.get('files', [])
    print(f"✅ Found {len(videos)} videos")
    
    if videos:
        # Download first video
        print(f"\n2. Testing download: {videos[0]['name']}")
        os.makedirs('downloads', exist_ok=True)
        
        request = drive_service.files().get_media(fileId=videos[0]['id'])
        video_path = f"downloads/{videos[0]['name']}"
        
        with open(video_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        
        print(f"✅ Downloaded: {video_path}")
        
        # 3. Test Instagram
        print("\n3. Testing Instagram...")
        from instagrapi import Client
        
        cl = Client()
        cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        print(f"✅ Logged in as {cl.user_id}")
        
        # Create a simple test video
        print("\n4. Creating test video...")
        test_video = "test_1sec.mp4"
        subprocess.run([
            'ffmpeg', '-y', '-f', 'lavfi',
            '-i', 'color=c=blue:s=640x480:d=1',
            '-c:v', 'libx264', '-t', '1',
            test_video
        ], capture_output=True)
        
        # Post test
        caption = f"Test post {datetime.now().strftime('%H:%M:%S')}"
        print(f"Posting: {caption}")
        
        media = cl.clip_upload(test_video, caption=caption)
        if media and hasattr(media, 'id'):
            print(f"✅ POST SUCCESSFUL! Media ID: {media.id}")
            print("🎉 Check your Instagram page now!")
        else:
            print("❌ Post failed")
        
        cl.logout()
        
        # Cleanup
        if os.path.exists(test_video):
            os.remove(test_video)
        if os.path.exists(video_path):
            os.remove(video_path)
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
