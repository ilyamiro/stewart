#!/usr/bin/env python3
"""Interactive YouTube OAuth 2.0 authentication script."""
import sys
import os
from pathlib import Path
from youtube.client import get_youtube_client, get_credentials_path, get_token_path

def main():
    print("=" * 65)
    print("YouTube Authentication Setup (OAuth 2.0)")
    print("=" * 65)

    client = get_youtube_client()
    token_file = get_token_path()
    print(f"Token storage destination: {token_file}")

    print("Checking current authentication status...")
    auth_status = client.check_auth()
    if auth_status.get("authenticated"):
        ch = auth_status.get("channel", {})
        print("\n✅ Already authenticated with YouTube!")
        if ch:
            print(f"Channel: {ch.get('title')} ({ch.get('custom_url') or ch.get('id')})")
            print(f"Subscribers: {ch.get('subscribers')} | Videos: {ch.get('video_count')}")
            print(f"Channel URL: {ch.get('url')}")
        else:
            print("Connected Google account has no public YouTube channel.")
        print(f"Token: {token_file}")
        return 0

    creds_file = get_credentials_path()
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not creds_file and not (client_id and client_secret):
        print("\n⚠️  No Google OAuth 2.0 Client credentials found!")
        print("\nTo set up YouTube access:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials")
        print("2. Ensure 'YouTube Data API v3' is enabled in your Google Cloud Project.")
        print("3. Place your client JSON at: ~/.config/life/calendar_credentials.json")
        print("   (Or set GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET in .env)")
        print("\nOnce placed, re-run 'bin/youtube-auth' to authenticate in your browser.\n")
        return 1

    print(f"\nFound credentials at: {creds_file or 'Environment variables'}")
    print("Starting local authorization server...")
    print("Your web browser will open automatically to authorize YouTube access.")

    res = client.authenticate_interactive()
    if "error" in res:
        print(f"\n❌ Authentication failed: {res['error']}")
        return 1

    ch = res.get("channel", {})
    print("\n🎉 YouTube authentication successful!")
    if ch:
        print(f"Connected Channel: {ch.get('title')} ({ch.get('custom_url') or ch.get('id')})")
        print(f"Subscribers: {ch.get('subscribers')} | Videos: {ch.get('video_count')}")
    print(f"Token saved to: {token_file}")
    print("\nYou can now search YouTube, view your channel, subscriptions, and playlists via Antigravity!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
