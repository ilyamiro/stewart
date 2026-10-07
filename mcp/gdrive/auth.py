#!/usr/bin/env python3
"""Interactive Google Drive OAuth 2.0 authentication script."""
import sys
import os
from pathlib import Path
from gdrive.client import get_drive_client, get_credentials_path, get_token_path

def main():
    print("=" * 65)
    print("Google Drive Authentication Setup (OAuth 2.0)")
    print("=" * 65)

    client = get_drive_client()
    token_file = get_token_path()
    print(f"Token storage destination: {token_file}")

    print("Checking current authentication status...")
    auth_status = client.check_auth()
    if auth_status.get("authenticated"):
        user = auth_status.get("user", {})
        storage = auth_status.get("storage", {})
        print("\n✅ Already authenticated with Google Drive!")
        print(f"User: {user.get('display_name')} ({user.get('email')})")
        print(f"Storage: {storage.get('used_gb')} GB / {storage.get('limit_gb')} GB ({storage.get('percent_used')}%)")
        print(f"Token: {token_file}")
        return 0

    creds_file = get_credentials_path()
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not creds_file and not (client_id and client_secret):
        print("\n⚠️  No Google OAuth 2.0 Client credentials found!")
        print("\nTo set up Google Drive access:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials")
        print("2. Create a project (or select an existing one) and enable 'Google Drive API'.")
        print("3. Go to 'Credentials' -> 'Create Credentials' -> 'OAuth client ID'.")
        print("4. Application type: Choose 'Desktop app' (name: 'Life Assistant').")
        print("5. Download the client secret JSON file.")
        print(f"6. Place it at: ~/.config/life/calendar_credentials.json (or ~/.config/life/drive_credentials.json)")
        print("   (Or set GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET in .env)")
        print("\nOnce placed, re-run 'bin/drive-auth' to authenticate in your browser.\n")
        return 1

    print(f"\nFound credentials at: {creds_file or 'Environment variables'}")
    print("Starting local authorization server...")
    print("Your web browser will open automatically to authorize Google Drive access.")

    res = client.authenticate_interactive()
    if "error" in res:
        print(f"\n❌ Authentication failed: {res['error']}")
        return 1

    user = res.get("user", {})
    storage = res.get("storage", {})
    print("\n🎉 Google Drive authentication successful!")
    print(f"Connected User: {user.get('display_name')} ({user.get('email')})")
    print(f"Storage: {storage.get('used_gb')} GB / {storage.get('limit_gb')} GB ({storage.get('percent_used')}%)")
    print(f"Token saved to: {token_file}")
    print("\nYou can now list, download, upload, and manage files on Google Drive via Antigravity!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
