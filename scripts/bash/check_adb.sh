#!/usr/bin/env bash

DEVICE_IP=$1

connected_device=$(adb devices | grep "$DEVICE_IP")

if [[ -n $connected_device ]]; then
    echo "true"
else
    echo "false"
fi