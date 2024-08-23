import json
import os.path
import subprocess
import logging
import sys
import yaml


def run(*args, stdout: bool = False):
    subprocess.run(
        args,
        stdout=subprocess.DEVNULL if not stdout else None,
        stderr=subprocess.STDOUT
    )


def system_setup():
    if sys.platform == "linux":
        run("jack_control", "start")


def yaml_load(path: str):
    if os.path.exists(path):
        with open(path) as file:
            return yaml.safe_load(file)


def json_load(path: str):
    if os.path.exists(path):
        with open(path) as file:
            return json.load(file)
