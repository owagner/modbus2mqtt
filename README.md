spicierModbus2mqtt
==================


Written and (C) 2018 Max Brueggemann <mail@maxbrueggemann.de> 
Contains code and documentation from modbus2mqtt, written and (C) 2015 Oliver Wagner <owagner@tellerulam.com> 
  
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


These issues are not likely to be resolved in modbus2mqtt because it has not seen any development in a while. So I decided to do a bit of a rewrite and change a couple of things. Unfortunately
this breaks compatibility with the original register definition files but there is no way
around it.

Dependencies
------------
* Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
* pymodbus - https://github.com/riptideio/pymodbus

Command line options
--------------------
    usage: modbus2mqtt.py [-h] [--mqtt-host MQTT_HOST] [--mqtt-port MQTT_PORT]
                          [--mqtt-topic MQTT_TOPIC] [--rtu RTU]
                          [--rtu-baud RTU_BAUD] [--rtu-parity {even,odd,none}]
                          --registers REGISTERS [--log LOG] [--syslog]
    
    optional arguments:
      -h, --help            show this help message and exit
      --mqtt-host MQTT_HOST
                            MQTT server address. Defaults to "localhost"
      --mqtt-port MQTT_PORT
                            MQTT server port. Defaults to 1883
      --mqtt-topic MQTT_TOPIC
                            Topic prefix to be used for subscribing/publishing.
                            Defaults to "modbus/"
      --clientid MQTT_CLIENT_ID
                            optional prefix for MQTT Client ID

      --rtu RTU             pyserial URL (or port name) for RTU serial port
      --rtu-baud RTU_BAUD   Baud rate for serial port. Defaults to 19200
      --rtu-parity {even,odd,none}
                            Parity for serial port. Defaults to even.
      --registers REGISTERS
                            Register specification file. Must be specified
      --force FORCE	    
                            optional interval (secs) to publish existing values
                            does not override a register's poll interval.
                            Defaults to 0 (publish only on change).
				
      --log LOG             set log level to the specified value. Defaults to
                            WARNING. Try DEBUG for maximum detail
      --syslog              enable logging to syslog

      
Register definition
-------------------
The Modbus registers which are to be polled are defined in a CSV file with
the following columns:

* *Topic suffix*
  The topic where the respective register will be published into. Will
  be prefixed with the global topic prefix and "status/".
* *Register offset*
  The register number, depending on the function code. Zero-based.
* *Size (in words)*
  The register size in words.
* *Format*
  The format how to interpret the register value. This can be two parts, split
  by a ":" character.
  The first part uses the Python
  "struct" module notation. Common examples:
    - >H unsigned short
    - >f float
  
  The second part is optional and specifies a Python format string, e.g.
      %.2f
  to format the value to two decimal digits.
* *Polling frequency*
    How often the register is to be polled, in seconds. Only integers.
* *SlaveID*
    The Modbus address of the slave to query. Defaults to 1.
* *FunctionCode*
  The Modbus function code to use for querying the register. Defaults
  to 4 (READ REGISTER). Only change if you know what you are doing.

Not all columns need to be specified. Unspecified columns take their
default values. The default values for subsequent rows can be set
by specifying a magic topic suffix of *DEFAULT*

Topics
------
Values are published as simple strings to topics with the general <prefix>,
the function code "/status/" and the topic suffix specified per register.
A value will only be published if it's textual representation has changed,
e.g. _after_ formatting has been applied. The published MQTT messages have
the retain flag set.

A special topic "<prefix>/connected" is maintained. 
It's a enum stating whether the module is currently running and connected to 
the broker (1) and to the Modbus interface (2).

Setting Modbus coils (FC=5) and registers (FC=6)
------------------------------------------------

modbus2mqtt subscibes to two topics:

- prefix/set/+/5/+  # where the first + is the slaveId and the second is the register
- prefix/set/+/6/+  # payload values are written the the devices (assumes 16bit Int)

There is only limited sanity checking currently on the payload values.
