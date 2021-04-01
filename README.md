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

Changelog
---------
- version 0.5, 21. of September 2019: print error messages in case of badly configured pollers
- version 0.4, 25. of May 2019: When writing to a device, updated states are now published immediately, if writing was successful.

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
- process deadbands for registers so MQTT values are only sent when the modbus register goes above or below the deadband.
- maybe do not poll if the poller only has references that are write-only
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
THE FIRST LINE OF THE CONFIG FILE HAS TO BE:

"type","topic","col2","col3","col4","col5","col6"

The Modbus data which is to be polled is defined in a CSV file.
There are two types of rows, each with different columns; a "Poller" object and a "Reference" object. In  the "Poller" object we define the type of the modbus data and how the request to the device should look like (which modbus references are to be read, for example: holding registers at references 0 to 10). With the reference object we define (among other things) to which topic the data of a certain data point (registers, coil..) is going to be published.
Modbus references are as transmitted on the wire. In the traditional numbering scheme these would have been called offsets. E. g. to read 400020 you would use reference 20.
Refer to the example.csv for more details.

* Use "coils", for modbus functioncode 1 
* Use "input status", for modbus functioncode 2
* Use "holding registers", for modbus functioncode 3
* Use "input registers", for modbus functioncode 4

Reference objects link to the modbus reference address and define specific details about that register or bit.
Pollers and references are used together like this:
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


Note that the reference addresses are absolute adresses and are NOT related to the start address of the poller! If you define a reference that is not within the pollers range you will get an error message.
So another example:
```
poll,someTopic,1,2,11,coil,1.0
ref,light9,9,rw
```
This will poll states of 11 coils from slave device 1 once a second, starting at coil 2.
The state of coil 9 will be published to mqtt with the topic modbus/someTopic/state/light0
if column 3 contains an 'r'.

If you publish a value (in case of a coil: True or False) to modbus/someTopic/set/light0 and
column 3 contains a 'w', the new state will be written to coil 9 of the slave device.


Some other "intepretations" of register contents are also supported:
```
poll,garage,1,0,10,holding_register,2
ref,counter1,0,rw,float32BE 
ref,counter2,2,rw,uint16
ref,somestring,3,rw,string6
```
This will poll 10 consecutive registers from Modbus slave id 1, starting at holding register 0.

The last row now contains the data format. Supported values: float32BE, float32LE, uint32BE, uint32LE, uint16 (default), stringXXX with XXX being the string length in bytes.

Note that a float32BE will of course span over two registers (0 and 1 in the above example) and that you can still define another reference object occupying the same registers. This might come in handy if you want to modify a small part of a string seperately.


Topics
------
Values are published as strings to topic:

"prefix/poller topic/state/reference topic"

A value will only be published if it's raw data has changed,
e.g. _before_ any formatting has been applied. The published MQTT messages have
the retain flag set.

A special topic "prefix/connected" is maintained. 
It states whether the module is currently running and connected to 
the broker (1) and to the Modbus interface (2).

We also maintain a "connected"-Topic for each poller (prefix/poller_topic/connected). This is useful when using Modbus RTU with multiple slave devices because a non-responsive device can be detected.

For diagnostic purposes (mainly for Modbus via serial) the topics prefix/poller_topic/state/diagnostics_errors_percent and prefix/poller_topic/state/diagnostics_errors_total are avaiable. This feature can be enabled by passing the argument "--diagnostics-rate X" with x being the amount of seconds between each recalculation and publishments of the error rate in percent and the amount of errors within the time frame X. Set X to something like 600 to get diagnostic messages every 10 minutes.

Writing to Modbus coils and registers
------------------------------------------------

spiciermodbus2mqtt subscribes to:

"prefix/poller topic/set/reference topic"


If you want to write to a coil:

mosquitto_pub -h <mqtt broker> -t modbus/somePoller/set/someReference -m "True"

to a register:

mosquitto_pub -h <mqtt broker> -t modbus/somePoller/set/someReference -m "12346"

Scripts addToHomeAssistant.py and create-openhab-conf.py
------------------------------------------------
These scripts are not really part of this project, but I decided to include them anyway. They were written because I grew more and more frustrated with the Modbus capabilities of OpenHAB and Home Assistant.

So what exactly do they do? Completely different things actually.

* addToHomeAssistant.py can only be run within modbus2mqtt.py. It can be invoked by passing --add-to-homeassistant when running modbus2mqtt.py. It uses MQTT messages to add all the stuff from the .csv file to home assistant automatically. Just try it. I recommend using a non productive instance of Home Assistant for testing :-)


* create-openhab-conf.py can be used independently. It parses the .csv file and creates configuration files (.things and .items) for OpenHAB (version 2+ only). This is of course not necessary for using spicierModbus2mqtt whit OpenHab but it removes a lot of hassle from it. I use it to create a basic working structure and then rename and rearrange the items by hand.
