#!/usr/bin/env python3
"""Interactive Telegram authentication script."""
import sys
import getpass
from telegram.client import get_telegram_manager

def main():
    print("=" * 60)
    print("Telegram MTProto Authentication Setup")
    print("=" * 60)

    mgr = get_telegram_manager()
    print(f"Session destination: {mgr.session_file}")

    print("Checking current authentication status...")
    status = mgr.check_auth()
    if status.get("authorized"):
        user = status.get("user", {})
        print("\n✅ Already authenticated!")
        print(f"User: {user.get('first_name')} {user.get('last_name') or ''} (@{user.get('username') or 'no-username'})")
        print(f"Phone: {user.get('phone')}")
        print(f"ID: {user.get('id')}")
        return 0

    print("\nAccount is not currently authenticated.")
    phone = input("\nEnter your phone number with country code (e.g. +45... or +380...): ").strip()
    if not phone:
        print("Phone number is required.")
        return 1

    print(f"Sending code to {phone}...")
    res = mgr.send_login_code(phone)
    if "error" in res:
        print(f"❌ Error sending code: {res['error']}")
        return 1

    print(f"✅ Code sent via {res.get('delivery_type', 'Telegram')}!")
    code = input("Enter the login code you received: ").strip()
    if not code:
        print("Login code is required.")
        return 1

    sign_res = mgr.sign_in(code=code, phone=phone)
    if sign_res.get("status") == "2fa_required":
        print("\nTwo-step verification (2FA) is enabled on your account.")
        password = getpass.getpass("Enter your Telegram 2FA cloud password: ")
        sign_res = mgr.sign_in(code=code, phone=phone, password=password)

    if "error" in sign_res:
        print(f"\n❌ Login failed: {sign_res['error']}")
        return 1

    user = sign_res.get("user", {})
    print("\n🎉 Authentication successful!")
    print(f"Logged in as: {user.get('first_name')} {user.get('last_name') or ''} (@{user.get('username') or 'no-username'})")
    print(f"Session saved to: {mgr.session_file}")
    print("\nYou can now ask Antigravity about your Telegram messages, unread chats, and more!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
