#!/usr/bin/env python3
"""
Test script to debug connections
"""

import json
import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    print("✅ Config loaded successfully")
    
    # Test Google Drive connection
    print("\n🔍 Testing Google Drive connection...")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    # Load credentials
    creds_dict = json.loads(config.GDRIVE_CREDENTIALS)
    
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    
    service = build('drive', 'v3', credentials=credentials)
    print("✅ Google Drive API connected")
    
    # List folders
    query = f"'{config.GDRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
    results = service.files().list(
        q=query,
        pageSize=10,
        fields="files(id, name)"
    ).execute()
    
    folders = results.get('files', [])
    print(f"📁 Found {len(folders)} folders:")
    for folder in folders:
        print(f"  - {folder['name']} (ID: {folder['id']})")
        
    # Test Facebook token
    print("\n🔍 Testing Facebook Access Token...")
    import requests
    
    # Test token validity
    test_url = f"https://graph.facebook.com/v18.0/{config.FACEBOOK_USER_ID}"
    params = {
        'access_token': config.FACEBOOK_ACCESS_TOKEN,
        'fields': 'id,name'
    }
    
    response = requests.get(test_url, params=params)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Facebook token valid")
        print(f"   User ID: {data.get('id')}")
        print(f"   Name: {data.get('name', 'Unknown')}")
    else:
        print(f"❌ Facebook token invalid: {response.status_code}")
        print(f"   Response: {response.text}")
        
    # Check Instagram connection
    print("\n🔍 Testing Instagram connection...")
    ig_url = f"https://graph.facebook.com/v18.0/{config.FACEBOOK_USER_ID}/accounts"
    ig_params = {
        'access_token': config.FACEBOOK_ACCESS_TOKEN,
        'fields': 'instagram_business_account{id,name,username}'
    }
    
    ig_response = requests.get(ig_url, params=ig_params)
    if ig_response.status_code == 200:
        data = ig_response.json()
        accounts = data.get('data', [])
        if accounts:
            for account in accounts:
                ig_account = account.get('instagram_business_account', {})
                if ig_account:
                    print(f"✅ Instagram account connected:")
                    print(f"   ID: {ig_account.get('id')}")
                    print(f"   Username: {ig_account.get('username')}")
        else:
            print("❌ No Instagram accounts found connected to this user")
    else:
        print(f"❌ Failed to get Instagram accounts: {ig_response.status_code}")
        print(f"   Response: {ig_response.text}")
        
except Exception as e:
    print(f"❌ Error during testing: {e}")
    import traceback
    traceback.print_exc()
