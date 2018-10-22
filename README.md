spicierModbus2mqtt
==================


Written and (C) 2018 Max Brueggemann <mail@maxbrueggemann.de> 
Contains code from modbus2mqtt, written and (C) 2015 Oliver Wagner <owagner@tellerulam.com> 
  
Provided under the terms of the MIT license.


Overview
--------
spicierModbus2mqtt is a Modbus master which continously polls slaves and publishes
values via MQTT.

It is intended as a building block in heterogenous smart home environments where 
an MQTT message broker is used as the centralized message bus.
See https://github.com/mqtt-smarthome for a rationale and architectural overview.

Why spicier?
------------
modbus2mqtt by Oliver Wagner is very nicely written but it has some major caveats:
- polling of consecutive references (coils/registers) is not done within a single modbus
  request. Instead there is a modbus request for every single reference which dramatically
  limits the performance of the whole bus.
- performance is limited to one modbus request per second artificially
- writing to a modbus slave device from the mqtt side requires knowledge about the location
  of data points (coils and registers) within the slave device.
- the library modbus_tk seems to have some unfixed bugs with multiple serial slave devices

These issues are not likely to be resolved in modbus2mqtt because it has not seen any development in a while. So I decided to do a bit of a rewrite and change a couple of things. A new structure of coil/register definitions was devised in order to poll consecutive registers in one request. Unfortunately this breaks compatibility with the original register definition files but there is no way around it 

Main improvements over modbus2mqtt:
- more abstraction when writing to coils/registers using mqtt. Writing is now
  possible without having to know slave id, reference, function code etc.
- specific coils/registers can be made read only
- multiple slave devices on one bus are now fully supported
- polling speed has been increased sgnificantly. With modbus RTU @ 38400 baud
  more than 80 transactions per second have been achieved.
- switched over to pymodbus which is in active development

There is still a lot of room for improvement! Especially in the realm of
- error handling
- documentation
- examples
- code style
...

So be careful :-)

Dependencies
------------
* python3
* Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
* pymodbus - https://github.com/riptideio/pymodbus

Installation of dependencies
----------------------------
* Install python3 and python3-pip (on a Debian based system something like sudo apt install python3 python3-pip will likely get you there)
* run pip3 install pymodbus
* run pip3 install paho-mqtt

Usage
--------------------
* fix me
* example for rtu and mqtt broker on localhost: python3 modbus2mqtt.py --rtu /dev/ttyS0 --rtu-baud 38400 --rtu-parity none --mqtt-host localhost  --config testing.csv
* example for tcp slave and mqtt broker on localhost: python3 modbus2mqtt.py --tcp localhost --config testing.csv

     
Configuration file
-------------------
The Modbus registers/coils which are to be polled are defined in a CSV file with
the following columns:

* *fix me*

Topics
------
Values are published as simple strings to topic.. fix me

A value will only be published if it's textual representation has changed,
e.g. _after_ formatting has been applied. The published MQTT messages have
the retain flag set.

A special topic "<prefix>/connected" is maintained. 
It's a enum stating whether the module is currently running and connected to 
the broker (1) and to the Modbus interface (2).

Writing to Modbus coils and registers
------------------------------------------------

modbus2mqtt subscibes to two topics:

- ../set/...  # where..

There is only limited sanity checking currently on the payload values.
