#!/usr/bin/env python3
"""Status verification for Open-Source Maps & Transit services."""
import sys
from gmaps.client import get_maps_client

def main():
    print("=" * 65)
    print("Open-Source Maps & Transit Service Status")
    print("=" * 65)

    client = get_maps_client()
    print("Checking open-source mapping backends...")
    status = client.check_auth()

    if status.get("authenticated"):
        print("\n✅ Open-Source Maps & Transit are 100% READY!")
        print("No API key, billing account, or credit card required.")
        print("\nActive providers:")
        for k, v in status.get("providers", {}).items():
            print(f" - {k.replace('_', ' ').capitalize()}: {v}")
        print("\nYou can immediately query bus schedules, travel times, directions, and places!")
        return 0
    else:
        print(f"\n❌ Connection issue: {status.get('error')}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
