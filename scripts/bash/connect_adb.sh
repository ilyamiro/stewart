#!/usr/bin/bash

DEVICE_IP=$1

sudo adb connect "$DEVICE_IP":5555
