modbus2mqtt
===========

  Written and (C) 2015 Oliver Wagner <owagner@tellerulam.com> 
  
  Provided under the terms of the MIT license.


Overview
--------
modbus2mqtt is a Modbus master which continously polls slaves and publishes
register values via MQTT.

It is intended as a building block in heterogenous smart home environments where 
an MQTT message broker is used as the centralized message bus.
See https://github.com/mqtt-smarthome for a rationale and architectural overview.


Dependencies
------------
* Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
* modbus-tk for Modbus communication - https://github.com/ljean/modbus-tk/


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


Changelog
---------
* 0.4 - 2015/07/31 - nzfarmer
  - added support for MQTT subscribe + Mobdus write
    Topics are of the form: prefix/set/<slaveid (0:255)>/<fc (5,6)>/<register>  (payload = value to write)
  - added CNTL-C for controlled exit
  - added --clientid for MQTT connections
  - added --force to repost register values regardless of change every x seconds where x >0
	
* 0.3 - 2015/05/26 - owagner
  - support optional string format specification
* 0.2 - 2015/05/26 - owagner
  - added "--rtu-parity" option to set the parity for RTU serial communication. Defaults to "even",
    to be inline with Modbus specification
  - changed default for "--rtu-baud" to 19200, to be inline with Modbus specification

* 0.1 - 2015/05/25 - owagner
  - Initial version
  
