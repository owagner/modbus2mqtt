import re
from setuptools import setup
 
 
version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('modbus2mqtt/modbus2mqtt.py').read(),
    re.M
    ).group(1)
 

# for some stupid reason we need restructured text here.
# For now I'll stick with markdown..
#with open("README.md", "rb") as f:
#    long_descr = f.read().decode("utf-8")
long_descr = ""

setup(
    name = "modbus2mqtt",
    packages = ["modbus2mqtt"],
    install_requires=[
          'paho-mqtt',
          'pymodbus',
          'serial',
    ],
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

