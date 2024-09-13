import requests
import re
from bs4 import BeautifulSoup
import lxml

headers = {
    "User-Agent": 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36'}


def getPublicIP():
    data = requests.get('https://2ip.io/', headers=headers).text
    soup = BeautifulSoup(data, "lxml")
    return soup.find('div', {'class': 'ip'}).find('span').text


def getInfo(ip: str):
    url = 'http://ipinfo.io/' + ip + '/json'
    info = requests.get(url, headers=headers).json()
    return info


def printInfo(info: dict):
    for key, value in info.items():
        if key != "readme":
            print(f"{key.capitalize()}: {value}")


def main():
    ip = getPublicIP()
    info = getInfo(ip)
    printInfo(info)


main()