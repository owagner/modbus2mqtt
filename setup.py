import re
from setuptools import setup
 
 
version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('modbus2mqtt/modbus2mqtt.py').read(),
    re.M
    ).group(1)
 
 
with open("README.md", "rb") as f:
    long_descr = f.read().decode("utf-8")

setup(
    name = "spicierModbus2mqtt",
    packages = ["modbus2mqtt"],
    entry_points = {
        "console_scripts": ['modbus2mqtt = modbus2mqtt.modbus2mqtt:main']
        },
    version = version,
    description = "Bridge from Modbus to MQTT",
    long_description = long_descr,
    author = "Max Brüggemann",
    author_email = "mail@maxbrueggemann.de",
    url = "https://github.com/mbs38/spicierModbus2mqtt",
    )

