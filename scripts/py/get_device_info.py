import requests
import re
from bs4 import BeautifulSoup
import lxml
import psutil
import json
import platform
import os
import subprocess


headers = {
    "User-Agent": 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'}


def getPublicIP():
    data = requests.get('https://2ip.io/', headers=headers).text
    soup = BeautifulSoup(data, "lxml")
    return soup.find('div', {'class': 'ip'}).find('span').text


def getInfo(ip: str):
    url = 'http://ipinfo.io/' + ip + '/json'
    ip_info = requests.get(url, headers=headers).json()
    return ip_info

#
# def printInfo(info: dict):
#     for key, value in info.items():
#         if key != "readme":
#             print(f"{key.capitalize()}: {value}")


def get_system_info():
    info = {
        "System": platform.system(),
        "System release": platform.release(),
        "System node":  platform.uname().node,
        "Full platform name": platform.platform(),
        "System version": platform.version(),
        "Machine": platform.machine(),
        "Python version": platform.python_version(),
        "Python compiler": platform.python_compiler(),
        "Python build": platform.python_build(),
        "Platform": platform.platform(),
    }
    return info


def get_disk_usage_linux():
    result = subprocess.run(['df', '-h'], stdout=subprocess.PIPE)
    output = result.stdout.decode('utf-8')

    # Split the output into lines
    lines = output.splitlines()

    # Extract the header and data lines
    data = []

    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 6:  # Ensure there are enough fields
            data.append({
                "Filesystem": fields[0],
                "Size": fields[1],
                "Used": fields[2],
                "Available": fields[3],
                "Use%": fields[4],
                "Mounted on": fields[5]
            })

    # Create a dictionary to hold the data

    return data


def write_to_file(data):
    with open("info.json", "w") as file:
        json.dump(data, file, indent=4)


if __name__ == '__main__':
    system = get_system_info()
    disk = get_disk_usage_linux()
    ip_info = getInfo(getPublicIP())

    dictionary = {
        "System": system,
        "Disk usage": disk,
        "Ip": ip_info
    }

    print(json.dumps(dictionary, indent=4))
    # write_to_file(dictionary)
