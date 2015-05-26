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


Register definition
-------------------
The Modbus registers which are to be polled are defined in a CSV file with
the following columns:

* Topic suffix
    The topic where the respective register will be published into. Will
    be prefixed with the global topic prefix and "status/".
* Register offset
    The register number, depending on the function code. Zero-based.
* Size (in words)
    The register size in words.
* Format
    The format how to interpret the register value. Uses the Python
    "struct" module notation. Common examples:
      - >H unsigned short
      - >f float
* Polling frequency
    How often the register is to be polled, in seconds. Only integers.
* SlaveID
    The Modbus address of the slave to query. Defaults to 1.
* FunctionCode
    The Modbus function code to use for querying the register. Defaults
    to 4 (READ REGISTER). Only change if you know what you are doing.

Not all columns need to be specified. Unspecified columns take their
default values. The default values for subsequent rows can be set
by specifying a magic topic suffix of *DEFAULT*


Changelog
---------
* 0.2 - 2015/05/26 - owagner
  - added "--rtu-parity" option to set the parity for RTU serial communication. Defaults to "even",
    to be inline with Modbus specification
  - changed default for "--rtu-baud" to 19200, to be inline with Modbus specification

* 0.1 - 2015/05/25 - owagner
  - Initial version
  
