#!/usr/bin/env python3
"""Interactive GitHub authentication script."""
import sys
import os
import subprocess
import getpass
from github_service.client import get_github_client, TOKEN_FILE

def main():
    print("=" * 65)
    print("GitHub Authentication Setup")
    print("=" * 65)

    client = get_github_client()
    print("Checking current GitHub authentication status...")
    status = client.check_auth()

    if status.get("authenticated"):
        user = status.get("user", {})
        print("\n✅ Already authenticated with GitHub!")
        print(f"Username: {user.get('login')}")
        print(f"Name: {user.get('name')}")
        print(f"Public Repos: {user.get('public_repos')}")
        print(f"Profile: {user.get('html_url')}")
        return 0

    print("\nNo active GitHub authentication found.")
    print("\nChoose authentication method:")
    print("1) Enter a Personal Access Token (Classic / Fine-grained)")
    print("2) Authenticate via official GitHub CLI ('gh auth login')")

    choice = input("\nEnter choice [1/2] (default 1): ").strip() or "1"

    if choice == "2":
        print("\nLaunching GitHub CLI authentication...")
        try:
            res = subprocess.run(["gh", "auth", "login"], check=True)
            print("\nRe-checking status...")
            client._gh = None
            new_status = client.check_auth()
            if new_status.get("authenticated"):
                u = new_status["user"]
                print(f"\n🎉 Successfully authenticated as {u.get('login')}!")
                return 0
            else:
                print("❌ Login did not complete.")
                return 1
        except Exception as e:
            print(f"Error running gh auth login: {e}")
            return 1

    print("\nTo generate a Personal Access Token:")
    print("1. Open https://github.com/settings/tokens (or fine-grained tokens).")
    print("2. Scopes recommended: 'repo', 'read:user', 'notifications'.")
    print("3. Generate token and paste it below.")

    token = getpass.getpass("\nPaste your GitHub Token: ").strip()
    if not token:
        print("Token cannot be empty.")
        return 1

    res = client.set_token(token)
    if not res.get("authenticated"):
        print(f"\n❌ Authentication failed: {res.get('error', 'Unknown error')}")
        return 1

    u = res["user"]
    print(f"\n🎉 Successfully authenticated as {u.get('login')} ({u.get('name') or ''})!")
    print(f"Token saved to: {TOKEN_FILE}")
    print("\nYou can now manage GitHub repos, issues, pull requests, and notifications via Antigravity!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
