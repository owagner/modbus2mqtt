spicierModbus2mqtt
==================


Written and (C) 2018 Max Brueggemann <mail@maxbrueggemann.de> 

Contains code from modbus2mqtt, written and (C) 2015 Oliver Wagner <owagner@tellerulam.com> 
  
Provided under the terms of the MIT license.


Overview
--------
spicierModbus2mqtt is a Modbus master which continuously polls slaves and publishes
values via MQTT.

It is intended as a building block in heterogeneous smart home environments where 
an MQTT message broker is used as the centralized message bus.
See https://github.com/mqtt-smarthome for a rationale and architectural overview.

Why spicier?
------------
modbus2mqtt by Oliver Wagner is very nicely written but it has some downsides:
- polling of consecutive references (coils/registers) is not done within a single modbus
  request. Instead there is a modbus request for every single reference which dramatically
  limits the performance of the whole bus.
- performance is limited to one modbus request per second artificially
- writing to a modbus slave device from the mqtt side requires knowledge about the location
  of data points (coils and registers) within the slave device.
- the library modbus_tk seems to have some unfixed bugs with multiple serial slave devices

These issues are not likely to be resolved in modbus2mqtt because it has not seen any development in a while. So I decided to do a bit of a rewrite and change a couple of things.

A new structure of coil/register definitions was devised in order to poll consecutive registers in one request. Unfortunately this breaks compatibility with the original register definition files but there is no way around it.

Main improvements over modbus2mqtt:
- more abstraction when writing to coils/registers using mqtt. Writing is now
  possible without having to know slave id, reference, function code etc.
- specific coils/registers can be made read only
- multiple slave devices on one bus are now fully supported
- polling speed has been increased significantly. With modbus RTU @ 38400 baud
  more than 80 transactions per second have been achieved.
- switched over to pymodbus which is in active development.
- Improved error handling, the software will continuously retry when the network or device goes down.

There is still a lot of room for improvement! Especially in the realm of
- documentation
- examples
- code style
- scaling of modbus registers before being sent to MQTT. 
- process deadbands for registers so MQTT values are only sent when the modbus register goes above or below the deadband.
...

So be careful :-)

Dependencies
------------
* python3
* Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
* pymodbus - https://github.com/riptideio/pymodbus

Installation of dependencies
----------------------------
* Install python3 and python3-pip and python3-serial (on a Debian based system something like sudo apt install python3 python3-pip python3-serial will likely get you there)
* run pip3 install pymodbus
* run pip3 install paho-mqtt

Usage
-----
* example for rtu and mqtt broker on localhost: python3 modbus2mqtt.py --rtu /dev/ttyS0 --rtu-baud 38400 --rtu-parity none --mqtt-host localhost  --config testing.csv
* example for tcp slave and mqtt broker
    on localhost: python3 modbus2mqtt.py --tcp localhost --config testing.csv
    remotely:     python3 modbus2mqtt.py --tcp 192.168.1.7 --config example.csv --mqtt-host iot.eclipse.org

     
Configuration file
-------------------
The Modbus data which is to be polled is defined in a CSV file.
There are two types of rows, each with different columns; a "Poller" object and a "Reference" object. In  the "Poller" object we define the type of the modbus data and how the request to the device should look like (which modbus references are to be read, for example: holding registers at references 0 to 10). With the reference object we define (among other things) to which topic the data of a certain data point (registers, coil..) is going to be published.
Modbus references are as transmitted on the wire. In the traditional numbering scheme these would have been called offsets. E. g. to read 400020 you would use reference 20.
Refer to the example.csv for more details.

Use "coils", for modbus functioncode 1 
Use "input status", for modbus functioncode 2
Use "holding registers", for modbus functioncode 3
Use "input registers", for modbus functioncode 4
Use "input registers_32BE", for modbus functioncode 4 where the two consecutive registers will be merged into a 32int.

Reference objects link to the modbus reference address and define specific details about that register or bit.
Example:

poller-object:
```
poll,someTopic,1,2,5,coil,1.0
```
Will poll states of 5 coils from slave device 1 once a second, starting at coil 2.

reference-object:
```
ref,light0,2,rw
```
The state of coil 2 will be published to mqtt with the topic modbus/someTopic/state/light0
if column 3 contains an 'r'.
If you publish a value (in case of a coil: True or False) to modbus/someTopic/set/light0 and
column 3 contains a 'w', the new state will be written to the slave device.

These are used together like this:
```
poll,kitchen,7,0,5,coil,1.0
ref,light0,0,rw
ref,light1,1,rw
ref,light2,2,rw
ref,light3,3,rw
ref,light4,4,rw
```
This will poll from Modbus slave id 7, starting at coil offset 0, for 5 coils, 1.0 times a second.

The first coil 0 will then be sent as an MQTT message with topic modbus/kitchen/state/light0.

The second coil 1 will then be sent as an MQTT message with topic modbus/kitchen/state/light1 and so on.


Topics
------
Values are published as strings to topic:

"prefix/poller topic/state/reference topic"

A value will only be published if it's textual representation has changed,
e.g. _after_ formatting has been applied. The published MQTT messages have
the retain flag set.

A special topic "<prefix>/connected" is maintained. 
It's a enum stating whether the module is currently running and connected to 
the broker (1) and to the Modbus interface (2).

Writing to Modbus coils and registers
------------------------------------------------

spiciermodbus2mqtt subscribes to:

"prefix/poller topic/set/reference topic"


say you want to write to a coil:

mosquitto_pub -h <mqtt broker> -t modbus/somePoller/set/someReference -m "True"

to a register:

mosquitto_pub -h <mqtt broker> -t modbus/somePoller/set/someReference -m "12346"
