#!/usr/bin/bash

DEVICE_IP=$1  # Take the device's IP address as an argument

# Check if the device is connected by looking at the output of 'adb devices'
connected_device=$(adb devices | grep "$DEVICE_IP")

if [[ -n $connected_device ]]; then
    echo "true"
else
    echo "false"
fi