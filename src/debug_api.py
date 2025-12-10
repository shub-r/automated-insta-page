#!/usr/bin/env python3
"""
Debug script to test Facebook Graph API connection
"""

import json
import requests
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Your credentials from GitHub Secrets
FACEBOOK_ACCESS_TOKEN = "EAAqfBXoEzHoBQOoKvaRFxKf3h8cCefVXbEOxi3Qn1yjOf1rlpoLKxJ39EJj0s3W2GEZCDSiwGSPZAmZAHSN3Tf4Uco9ZBlIzwisZBKzHaKdOLMIeExwvKqOcBbyM4WDZCyvrHPfHRmZB2ZCoQ7MWYDVfRNkBSZCbrdZBmkXZBFdi6znYe9vmbZCvIjhrousCxilBlZCL1"
FACEBOOK_USER_ID = "122093738433160699"
FACEBOOK_GRAPH_URL = "https://graph.facebook.com/v18.0"

def test_token():
    """Test if the access token is valid"""
    logger.info("Testing Facebook Access Token...")
    
    url = f"{FACEBOOK_GRAPH_URL}/me"
    params = {
        'access_token': FACEBOOK_ACCESS_TOKEN,
        'fields': 'id,name,email'
    }
    
    try:
        response = requests.get(url, params=params)
        logger.info(f"Token test status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Token is valid! User info: {json.dumps(data, indent=2)}")
            return True
        else:
            logger.error(f"Token test failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error testing token: {e}")
        return False

def test_pages():
    """Test if we can access pages"""
    logger.info("Testing Facebook Pages access...")
    
    url = f"{FACEBOOK_GRAPH_URL}/me/accounts"
    params = {
        'access_token': FACEBOOK_ACCESS_TOKEN,
        'fields': 'id,name,access_token,instagram_business_account'
    }
    
    try:
        response = requests.get(url, params=params)
        logger.info(f"Pages test status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Pages data: {json.dumps(data, indent=2)}")
            
            # Check for Instagram business accounts
            pages = data.get('data', [])
            for page in pages:
                if 'instagram_business_account' in page:
                    ig_account = page['instagram_business_account']
                    logger.info(f"Found Instagram Business Account: {ig_account}")
                    
                    # Get Instagram account details
                    ig_url = f"{FACEBOOK_GRAPH_URL}/{ig_account.get('id') if isinstance(ig_account, dict) else ig_account}"
                    ig_params = {
                        'access_token': FACEBOOK_ACCESS_TOKEN,
                        'fields': 'id,name,username,profile_picture_url'
                    }
                    
                    ig_response = requests.get(ig_url, params=ig_params)
                    if ig_response.status_code == 200:
                        ig_data = ig_response.json()
                        logger.info(f"Instagram Account Details: {json.dumps(ig_data, indent=2)}")
            
            return True
        else:
            logger.error(f"Pages test failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error testing pages: {e}")
        return False

def test_permissions():
    """Test what permissions the token has"""
    logger.info("Testing token permissions...")
    
    url = f"{FACEBOOK_GRAPH_URL}/me/permissions"
    params = {
        'access_token': FACEBOOK_ACCESS_TOKEN
    }
    
    try:
        response = requests.get(url, params=params)
        logger.info(f"Permissions test status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Permissions: {json.dumps(data, indent=2)}")
            
            # Check for required permissions
            required_permissions = [
                'instagram_basic',
                'instagram_content_publish',
                'pages_read_engagement',
                'pages_show_list'
            ]
            
            granted_permissions = [perm['permission'] for perm in data.get('data', []) if perm['status'] == 'granted']
            
            logger.info(f"Granted permissions: {granted_permissions}")
            
            missing = [perm for perm in required_permissions if perm not in granted_permissions]
            if missing:
                logger.error(f"Missing required permissions: {missing}")
                return False
            else:
                logger.info("All required permissions are granted!")
                return True
        else:
            logger.error(f"Permissions test failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error testing permissions: {e}")
        return False

def test_user_id():
    """Test the provided Facebook User ID"""
    logger.info(f"Testing Facebook User ID: {FACEBOOK_USER_ID}")
    
    url = f"{FACEBOOK_GRAPH_URL}/{FACEBOOK_USER_ID}"
    params = {
        'access_token': FACEBOOK_ACCESS_TOKEN,
        'fields': 'id,name,link,instagram_business_account'
    }
    
    try:
        response = requests.get(url, params=params)
        logger.info(f"User ID test status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"User ID info: {json.dumps(data, indent=2)}")
            
            if 'instagram_business_account' in data:
                logger.info("This ID has an Instagram Business Account connected!")
                return True
            else:
                logger.warning("This ID does not have an Instagram Business Account connected")
                return False
        else:
            logger.error(f"User ID test failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error testing user ID: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("FACEBOOK GRAPH API DEBUG SCRIPT")
    logger.info("=" * 60)
    
    tests = [
        ("Access Token", test_token),
        ("Permissions", test_permissions),
        ("Pages", test_pages),
        ("User ID", test_user_id)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*40}")
        logger.info(f"Running: {test_name}")
        logger.info('='*40)
        
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))
    
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info('='*60)
    
    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 All tests passed! The API should work correctly.")
    else:
        logger.info("\n⚠️  Some tests failed. Check the logs above for details.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
