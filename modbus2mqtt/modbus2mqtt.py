# spicierModbus2mqtt - Modbus TCP/RTU to MQTT bridge (and vice versa)
# https://github.com/mbs38/spicierModbus2mqtt 
#
# Written in 2018 by Max Brueggemann <mail@maxbrueggemann.de>
#  
#
# Provided under the terms of the MIT license.

# Contains a bunch of code taken from:
# modbus2mqtt - Modbus master with MQTT publishing
# Written and (C) 2015 by Oliver Wagner <owagner@tellerulam.com>
# Provided under the terms of the MIT license.

# Main improvements over modbus2mqtt:
# - more abstraction when writing to coils/registers using mqtt. Writing is now
#   possible without having to know slave id, reference, function code etc.
# - specific coils/registers can be made read only
# - multiple slave devices on one bus are now supported
# - polling speed has been increased sgnificantly. With modbus RTU @ 38400 baud
#   more than 80 transactions per second have been achieved.
# - switched over to pymodbus which is in active development


# Requires:
# - Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
# - pymodbus - https://github.com/riptideio/pymodbus
#!/usr/bin/env python

import argparse
import time
import socket
import paho.mqtt.client as mqtt
import serial
import io
import sys
import csv
import signal
import random
import ssl
import math
import struct
import queue

from .addToHomeAssistant import HassConnector
from .dataTypes import DataTypes

import pymodbus
import asyncio

from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusTlsClient,
    AsyncModbusUdpClient,
)
from pymodbus.exceptions import ModbusIOException

__version__ = "0.72"
mqtt_port = None
mqc = None
parser = None
args = None
verbosity = None
addToHass = None
loopBreak = None
globaltopic = None
pollers = []
deviceList = []
referenceList = []
master = None
control = None

writeQueue = queue.SimpleQueue()

class Control:
    def __init__(self):
        self.runLoop = True
    def stopLoop(self):
        self.runLoop = False

def signal_handler(signal, frame):
        global control
        print('Exiting ' + sys.argv[0])
        control.stopLoop()

class Device:
    def __init__(self,name,slaveid):
        self.name=name
        self.occupiedTopics=[]
        self.writableReferences=[]
        self.slaveid=slaveid
        self.errorCount=0
        self.pollCount=0
        self.next_due=time.clock_gettime(0)+args.diagnostics_rate
        if verbosity>=2:
            print('Added new device \"'+self.name+'\"')

    def publishDiagnostics(self):
        if args.diagnostics_rate>0:
            if self.next_due<time.clock_gettime(0):
                self.next_due=time.clock_gettime(0)+args.diagnostics_rate
                error=0
                try:
                    error=(self.errorCount / self.pollCount)*100
                except:
                    error=0
                if self.pollCount==0:
                    error=100
                if mqc.initial_connection_made == True:
                    try:
                        mqc.publish(globaltopic + self.name +"/state/diagnostics_errors_percent", str(error), qos=1, retain=True)
                        mqc.publish(globaltopic + self.name +"/state/diagnostics_errors_total", str(self.errorCount), qos=1, retain=True)
                    except:
                        pass
                self.pollCount=0
                self.errorCount=0

class Poller:
    def __init__(self,topic,rate,slaveid,functioncode,reference,size,dataType):
        self.topic=topic
        self.rate=float(rate)
        self.slaveid=int(slaveid)
        self.functioncode=int(functioncode)
        self.dataType=dataType
        self.reference=int(reference)
        self.size=int(size)
        self.next_due=time.clock_gettime(0)+self.rate*random.uniform(0,1)
        self.last = None
        self.readableReferences=[]
        self.device=None
        self.disabled=False
        self.failcounter=0
        self.connected=False

        for myDev in deviceList:
            if myDev.name == self.topic:
                self.device=myDev
                break
        if self.device == None:
            device = Device(self.topic,slaveid)
            deviceList.append(device)
            self.device=device
        if verbosity>=2:
            print("Added new poller "+str(self.topic)+","+str(self.functioncode)+","+str(self.dataType)+","+str(self.reference)+","+str(self.size)+",")


    def failCount(self,failed):
        self.device.pollCount+=1
        if not failed:
            self.failcounter=0
            if not self.connected:
                self.connected = True
                mqc.publish(globaltopic + self.topic +"/connected", "True", qos=1, retain=True)
        else:
            self.device.errorCount+=1
            if self.failcounter==3:
                if args.autoremove:
                    self.disabled=True
                    if verbosity >=1:
                        print("Poller "+self.topic+" with Slave-ID "+str(self.slaveid)+" disabled (functioncode: "+str(self.functioncode)+", start reference: "+str(self.reference)+", size: "+str(self.size)+").")
                    for p in pollers: #also fail all pollers with the same slave id
                        if p.slaveid == self.slaveid:
                            p.failcounter=3
                            p.disabled=True
                            if verbosity >=1:
                                print("Poller "+p.topic+" with Slave-ID "+str(p.slaveid)+" disabled (functioncode: "+str(p.functioncode)+", start reference: "+str(p.reference)+", size: "+str(p.size)+").")
                self.failcounter=4
                self.connected = False
                mqc.publish(globaltopic + self.topic +"/connected", "False", qos=1, retain=True)
            else:
                if self.failcounter<3:
                    self.failcounter+=1

    async def poll(self):
            result = None
            failed = False
            try:
                time.sleep(0.002)
                if self.functioncode == 3:
                    result = await master.read_holding_registers(self.reference, self.size, slave=self.slaveid)
                    if result.function_code < 0x80:
                        data = result.registers
                    else:
                        failed = True
                if self.functioncode == 1:
                    result = await master.read_coils(self.reference, self.size, slave=self.slaveid)
                    if result.function_code < 0x80:
                        data = result.bits
                    else:
                        failed = True
                if self.functioncode == 2:
                    result = await master.read_discrete_inputs(self.reference, self.size, slave=self.slaveid)
                    if result.function_code < 0x80:
                        data = result.bits
                    else:
                        failed = True
                if self.functioncode == 4:
                    result = await master.read_input_registers(self.reference, self.size, slave=self.slaveid)
                    if result.function_code < 0x80:
                        data = result.registers
                    else:
                        failed = True
                if not failed:
                    if verbosity>=4:
                        print("Read MODBUS, FC:"+str(self.functioncode)+", DataType:"+str(self.dataType)+", ref:"+str(self.reference)+", Qty:"+str(self.size)+", SI:"+str(self.slaveid))
                        print("Read MODBUS, DATA:"+str(data))
                    for ref in self.readableReferences:
                        val = data[ref.relativeReference:(ref.regAmount+ref.relativeReference)]
                        ref.checkPublish(val)
                else:
                    if verbosity>=1:
                        print("Slave device "+str(self.slaveid)+" responded with error code:"+str(result).split(',', 3)[2].rstrip(')'))
            except Exception as e:
                failed = True
                if verbosity>=1:
                    print("Error talking to slave device:"+str(self.slaveid)+" ("+str(e)+")")
            self.failCount(failed)

    async def checkPoll(self):
        if time.clock_gettime(0) >= self.next_due and not self.disabled:
            await self.poll()
            self.next_due=time.clock_gettime(0)+self.rate

    def addReference(self,myRef):
        #check reference configuration and maybe add to this poller or to the list of writable things
        if myRef.topic not in self.device.occupiedTopics:
            self.device.occupiedTopics.append(myRef.topic)
            
            if "r" in myRef.rw or "w" in myRef.rw:
                myRef.device=self.device
                if verbosity >= 2:
                    print('Added new reference \"' + myRef.topic + '\"')
                if "r" in myRef.rw:
                    if myRef.checkSanity(self.reference,self.size):
                        self.readableReferences.append(myRef)
                        if "w" not in myRef.rw:
                            referenceList.append(myRef)

                    else:
                        print("Reference \""+str(myRef.reference)+"\" with topic "+myRef.topic+" is not in range ("+str(self.reference)+" to "+str(int(self.reference+self.size-1))+") of poller \""+self.topic+"\", therefore ignoring it for polling.")
                if "w" in myRef.rw:
                    if self.functioncode == 3: #holding registers
                        myRef.writefunctioncode=6 #preset single register
                    if self.functioncode == 1: #coils
                        myRef.writefunctioncode=5 #force single coil
                    if self.functioncode == 2: #read input status, not writable
                        print("Reference \""+str(myRef.reference)+"\" with topic "+myRef.topic+" in poller \""+self.topic+"\" is not writable (discrete input)")
                    if self.functioncode == 4: #read input register, not writable
                        print("Reference \""+str(myRef.reference)+"\" with topic "+myRef.topic+" in poller \""+self.topic+"\" is not writable (input register)")
                    if myRef.writefunctioncode is not None:
                       self.device.writableReferences.append(myRef)
                       referenceList.append(myRef)
            else:
                print("Reference \""+str(myRef.reference)+"\" with topic "+myRef.topic+" in poller \""+self.topic+"\" is neither read nor writable, therefore ignoring it.")
        else:
            print("Reference topic ("+str(myRef.topic)+") is already occupied for poller \""+self.topic+"\", therefore ignoring it.")

class Reference:
    def __init__(self,topic,reference,dtype,rw,poller,scaling):
        self.topic=topic
        self.reference=int(reference)
        self.lastval=None
        self.scale=None
        self.regAmount=None
        self.stringLength=None

        if scaling:
            try:
                self.scale=float(scaling)
            except ValueError as e:
              if verbosity>=1:
                print("Scaling Error:", e)
        self.rw=rw
        self.relativeReference=None
        self.writefunctioncode=None
        self.device=None
        self.poller=poller
        if self.poller.functioncode == 1:
            DataTypes.parseDataType(self,"bool")
            
        elif self.poller.functioncode == 2:
            DataTypes.parseDataType(self,"bool")
        else:
            DataTypes.parseDataType(self,dtype)

    def checkSanity(self,reference,size):
        if self.reference in range(reference,size+reference) and self.reference+self.regAmount-1 in range(reference,size+reference):
            self.relativeReference=self.reference-reference
            return True

    def checkPublish(self,val):
        # Only publish messages after the initial connection has been made. If it became disconnected then the offline buffer will store messages,
        # but only after the intial connection was made.
        if mqc.initial_connection_made == True:
            val = self.combine(self,val)
            if self.lastval != val or args.always_publish:
                self.lastval = val
                if self.scale:
                    val = val * self.scale
                try:
                    publish_result = mqc.publish(globaltopic+self.device.name+"/state/"+self.topic,val,retain=True)
                    if verbosity>=4:
                        print("published MQTT topic: " + str(self.device.name+"/state/"+self.topic)+" value: " + str(self.lastval)+" RC:"+str(publish_result.rc))
                except:
                    if verbosity>=1:
                        print("Error publishing MQTT topic: " + str(self.device.name+"/state/"+self.topic)+"value: " + str(self.lastval))

async def writehandler(userdata,msg):
    if str(msg.topic) == globaltopic+"reset-autoremove":
        if not args.autoremove and verbosity>=1:
            print("ERROR: Received autoremove-reset command but autoremove is not enabled. Check flags.")
        if args.autoremove:
            payload = str(msg.payload.decode("utf-8"))
            if payload == "True" or payload == "1":
                if verbosity>=1:
                    print("Reactivating previously disabled pollers (command from MQTT)")
                for p in pollers:
                    if p.disabled == True:
                        p.disabled = False
                        p.failcounter = 0
                        if verbosity>=1:
                            print("Reactivated poller "+p.topic+" with Slave-ID "+str(p.slaveid)+ " and functioncode "+str(p.functioncode)+".")

        return
    (prefix,device,function,reference) = msg.topic.split("/")
    if function != 'set':
        return
    myRef = None
    myDevice = None
    for iterDevice in deviceList:
        if iterDevice.name == device:
            myDevice = iterDevice
    if myDevice == None: # no such device
        return
    for iterRef in myDevice.writableReferences:
        if iterRef.topic == reference:
            myRef=iterRef
    if myRef == None: # no such reference
        return    
    payload = str(msg.payload.decode("utf-8"))
    time.sleep(0.002)
    if myRef.writefunctioncode == 5:
        value = myRef.parse(myRef,str(payload))
        if value != None:
                result = await master.write_coil(int(myRef.reference),value,slave=int(myRef.device.slaveid))
                try:
                    if result.function_code < 0x80:
                        myRef.checkPublish(value) # writing was successful => we can assume, that the corresponding state can be set and published
                        if verbosity>=3:
                            print("Writing coils values to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" successful.")
                    else:
                        if verbosity>=1:
                            print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" FAILED! (Devices responded with errorcode"+str(result).split(',', 3)[2].rstrip(')')+". Maybe bad configuration?)")
            
                except:
                    if verbosity>=1:
                        print("Error writing to slave device "+str(myDevice.slaveid)+" (maybe CRC error or timeout)")
        else:
            if verbosity >= 1:
                print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" not possible. Given value is not \"True\" or \"False\".")


    if myRef.writefunctioncode == 6:
        value = myRef.parse(myRef,str(payload))
        if value is not None:
            try:
                valLen=len(value)
            except:
                valLen=1
            if valLen>1 or args.avoid_fc6:
                result = await master.write_registers(int(myRef.reference),value,slave=myRef.device.slaveid)
            else:
                result = await master.write_register(int(myRef.reference),value,slave=myRef.device.slaveid)
            try:
                if result.function_code < 0x80:
                    myRef.checkPublish(value) # writing was successful => we can assume, that the corresponding state can be set and published
                    if verbosity>=3:
                        print("Writing register value(s) to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" successful.")
                else:
                    if verbosity>=1:
                        print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" FAILED! (Devices responded with errorcode"+str(result).split(',', 3)[2].rstrip(')')+". Maybe bad configuration?)")
            except:
                if verbosity >= 1:
                    print("Error writing to slave device "+str(myDevice.slaveid)+" (maybe CRC error or timeout)")
        else:
            if verbosity >= 1:
                print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" not possible. Value does not fulfill criteria.")

def messagehandler(mqc,userdata,msg):
    writeQueue.put((userdata, msg))

def connecthandler(mqc,userdata,flags,rc):
    if rc == 0:
        mqc.initial_connection_made = True
        if verbosity>=2:
            print("MQTT Broker connected succesfully: " + args.mqtt_host + ":" + str(mqtt_port))
        mqc.subscribe(globaltopic + "+/set/+")
        mqc.subscribe(globaltopic + "reset-autoremove")
        if verbosity>=2:
            print("Subscribed to MQTT topic: "+globaltopic + "+/set/+")
        mqc.publish(globaltopic + "connected", "True", qos=1, retain=True)
    elif rc == 1:
        if verbosity>=1:
            print("MQTT Connection refused – incorrect protocol version")
    elif rc == 2:
        if verbosity>=1:
            print("MQTT Connection refused – invalid client identifier")
    elif rc == 3:
        if verbosity>=1:
            print("MQTT Connection refused – server unavailable")
    elif rc == 4:
        if verbosity>=1:
            print("MQTT Connection refused – bad username or password")
    elif rc == 5:
        if verbosity>=1:
            print("MQTT Connection refused – not authorised")

def disconnecthandler(mqc,userdata,rc):
    if verbosity >= 2:
        print("MQTT Disconnected, RC:"+str(rc))

def loghandler(mgc, userdata, level, buf):
    if verbosity >= 4:
        print("MQTT LOG:" + buf)

def main():
    asyncio.run(async_main(), debug=False)

async def async_main():
    global parser
    global args
    global verbosity 
    global addToHass
    global loopBreak
    global globaltopic
    global control

    parser = argparse.ArgumentParser(description='Bridge between ModBus and MQTT')
    parser.add_argument('--mqtt-host', default='localhost', help='MQTT server address. Defaults to "localhost"')
    parser.add_argument('--mqtt-port', default=None, type=int, help='Defaults to 8883 for TLS or 1883 for non-TLS')
    parser.add_argument('--mqtt-topic', default='modbus/', help='Topic prefix to be used for subscribing/publishing. Defaults to "modbus/"')
    parser.add_argument('--mqtt-user', default=None, help='Username for authentication (optional)')
    parser.add_argument('--mqtt-pass', default="", help='Password for authentication (optional)')
    parser.add_argument('--mqtt-use-tls', action='store_true', help='Use TLS')
    parser.add_argument('--mqtt-insecure', action='store_true', help='Use TLS without providing certificates')
    parser.add_argument('--mqtt-cacerts', default=None, help="Path to keychain including ")
    parser.add_argument('--mqtt-tls-version', default=None, help='TLS protocol version, can be one of tlsv1.2 tlsv1.1 or tlsv1')
    parser.add_argument('--rtu',help='pyserial URL (or port name) for RTU serial port')
    parser.add_argument('--rtu-baud', default='19200', type=int, help='Baud rate for serial port. Defaults to 19200')
    parser.add_argument('--rtu-parity', default='even', choices=['even','odd','none'], help='Parity for serial port. Defaults to even')
    parser.add_argument('--tcp', help='Act as a Modbus TCP master, connecting to host TCP')
    parser.add_argument('--tcp-port', default='502', type=int, help='Port for MODBUS TCP. Defaults to 502')
    parser.add_argument('--set-modbus-timeout',default='1',type=float, help='Response time-out for MODBUS devices')
    parser.add_argument('--config', required=True, help='Configuration file. Required!')
    parser.add_argument('--verbosity', default='3', type=int, help='Verbose level, 0=silent, 1=errors only, 2=connections, 3=mb writes, 4=all')
    parser.add_argument('--autoremove',action='store_true',help='Automatically remove poller if modbus communication has failed three times. Removed pollers can be reactivated by sending "True" or "1" to topic modbus/reset-autoremove')
    parser.add_argument('--add-to-homeassistant',action='store_true',help='Add devices to Home Assistant using Home Assistant\'s MQTT-Discovery')
    parser.add_argument('--always-publish',action='store_true',help='Always publish values, even if they did not change.')
    parser.add_argument('--set-loop-break',default=None,type=float, help='Set pause in main polling loop. Defaults to 10ms.')
    parser.add_argument('--diagnostics-rate',default='0',type=int, help='Time in seconds after which for each device diagnostics are published via mqtt. Set to sth. like 600 (= every 10 minutes) or so.')
    parser.add_argument('--avoid-fc6',action='store_true', help='If set, use function code 16 (write multiple registers) even when just writing a single register')
    control = Control()
    signal.signal(signal.SIGINT, signal_handler)

    args=parser.parse_args()
    verbosity=args.verbosity
    loopBreak=args.set_loop_break
    if loopBreak is None:
        loopBreak=0.01
    addToHass=False
    addToHass=args.add_to_homeassistant
    
    globaltopic=args.mqtt_topic
    
    if not globaltopic.endswith("/"):
        globaltopic+="/"
    
    if verbosity>=0:
        print('Starting spiciermodbus2mqtt V%s with topic prefix \"%s\"' %(__version__, globaltopic))

    # type, topic, slaveid,  ref,           size, functioncode, rate
    # type, topic, reference, rw, interpretation,      scaling,
    
    # Now let's read the config file
    with open(args.config,"r") as csvfile:
        csvfile.seek(0)
        reader=csv.DictReader(csvfile)
        currentPoller=None
        for row in reader:
            if row["type"]=="poller" or row["type"]=="poll":
                rate = float(row["col6"])
                slaveid = int(row["col2"])
                reference = int(row["col3"])
                size = int(row["col4"])
                
                if row["col5"] == "holding_register":
                    functioncode = 3
                    dataType="int16"
                    if size>123: #applies to TCP, RTU should support 125 registers. But let's be safe.
                        currentPoller=None
                        if verbosity>=1:
                            print("Too many registers (max. 123). Ignoring poller "+row["topic"]+".")
                        continue
                elif row["col5"] == "coil":
                    functioncode = 1
                    dataType="bool"
                    if size>2000: #some implementations don't seem to support 2008 coils/inputs
                        currentPoller=None
                        if verbosity>=1:
                            print("Too many coils (max. 2000). Ignoring poller "+row["topic"]+".")
                        continue
                elif row["col5"] == "input_register":
                    functioncode = 4
                    dataType="int16"
                    if size>123:
                        currentPoller=None
                        if verbosity>=1:
                            print("Too many registers (max. 123). Ignoring poller "+row["topic"]+".")
                        continue
                elif row["col5"] == "input_status":
                    functioncode = 2
                    dataType="bool"
                    if size>2000:
                        currentPoller=None
                        if verbosity>=1:
                            print("Too many inputs (max. 2000). Ignoring poller "+row["topic"]+".")
                        continue
    
                else:
                    print("Unknown function code ("+row["col5"]+" ignoring poller "+row["topic"]+".")
                    currentPoller=None
                    continue
                currentPoller = Poller(row["topic"],rate,slaveid,functioncode,reference,size,dataType)
                pollers.append(currentPoller)
                continue
            elif row["type"]=="reference" or row["type"]=="ref":
                if currentPoller is not None:
                    currentPoller.addReference(Reference(row["topic"],row["col2"],row["col4"],row["col3"],currentPoller,row["col5"]))
                else:
                    print("No poller for reference "+row["topic"]+".")
    
    #Setup MODBUS Master
    global master
    if args.rtu:
        if args.rtu_parity == "none":
                parity = "N"
        if args.rtu_parity == "odd":
                parity = "O"
        if args.rtu_parity == "even":
                parity = "E"
        master = AsyncModbusSerialClient(port=args.rtu, stopbits = 1, bytesize = 8, parity = parity, baudrate = int(args.rtu_baud), timeout=args.set_modbus_timeout)
    
    elif args.tcp:
        master = AsyncModbusTcpClient(args.tcp, port=args.tcp_port,client_id="modbus2mqtt", clean_session=False)
    else:
        print("You must specify a modbus access method, either --rtu or --tcp")
        sys.exit(1)
    
    #Setup MQTT Broker
    global mqtt_port
    mqtt_port = args.mqtt_port
    
    if mqtt_port is None:
        if args.mqtt_use_tls:
            mqtt_port = 8883
        else:
            mqtt_port = 1883
    
    clientid=globaltopic + "-" + str(time.time())
    global mqc
    mqc=mqtt.Client(client_id=clientid)
    mqc.on_connect=connecthandler
    mqc.on_message=messagehandler
    mqc.on_disconnect=disconnecthandler
    mqc.on_log= loghandler
    mqc.will_set(globaltopic+"connected","False",qos=2,retain=True)
    mqc.initial_connection_attempted = False
    mqc.initial_connection_made = False
    if args.mqtt_user or args.mqtt_pass:
        mqc.username_pw_set(args.mqtt_user, args.mqtt_pass)
    
    if args.mqtt_use_tls:
        if args.mqtt_tls_version == "tlsv1.2":
            tls_version = ssl.PROTOCOL_TLSv1_2
        elif args.mqtt_tls_version == "tlsv1.1":
            tls_version = ssl.PROTOCOL_TLSv1_1
        elif args.mqtt_tls_version == "tlsv1":
            tls_version = ssl.PROTOCOL_TLSv1
        elif args.mqtt_tls_version is None:
            tls_version = None
        else:
            if verbosity >= 2:
                print("Unknown TLS version - ignoring")
            tls_version = None
    
        if args.mqtt_insecure:
            cert_regs = ssl.CERT_NONE
        else:
            cert_regs = ssl.CERT_REQUIRED
    
        mqc.tls_set(ca_certs=args.mqtt_cacerts, certfile= None, keyfile=None, cert_reqs=cert_regs, tls_version=tls_version)
    
        if args.mqtt_insecure:
            mqc.tls_insecure_set(True)
    
    if len(pollers)<1:
        print("No pollers. Exitting.")
        sys.exit(0)
    
    #Main Loop
    modbus_connected = False
    current_poller = 0
    while control.runLoop:
        time.sleep(loopBreak)
        modbus_connected = master.connected
        if not modbus_connected:
            print("Connecting to MODBUS...")
            await master.connect()
            modbus_connected = master.connected
            if modbus_connected:
                if verbosity >= 2:
                    print("MODBUS connected successfully")
            else:
                for p in pollers:
                    p.failed=True
                    if p.failcounter<3:
                        p.failcounter=3
                    p.failCount(p.failed)
                if verbosity >= 1:
                    print("MODBUS connection error (mainLoop), trying again...")
                time.sleep(0.5)
    
        if not mqc.initial_connection_attempted:
           try:
                print("Connecting to MQTT Broker: " + args.mqtt_host + ":" + str(mqtt_port) + "...")
                mqc.connect(args.mqtt_host, mqtt_port, 60)
                mqc.initial_connection_attempted = True #Once we have connected the mqc loop will take care of reconnections.
                mqc.loop_start()
                #Setup HomeAssistant
                if(addToHass):
                    adder=HassConnector(mqc,globaltopic,verbosity>=1)
                    adder.addAll(referenceList)
                if verbosity >= 1:
                    print("MQTT Loop started")
           except:
                if verbosity>=1:
                    print("Socket Error connecting to MQTT broker: " + args.mqtt_host + ":" + str(mqtt_port) + ", check LAN/Internet connection, trying again...")
    
        if mqc.initial_connection_made: #Don't start polling unless the initial connection to MQTT has been made, no offline MQTT storage will be available until then.
            if modbus_connected:
                try:
                    if len(pollers) > 0:
                        await pollers[current_poller].checkPoll()
                        current_poller = current_poller + 1
                        if current_poller == len(pollers):
                            current_poller=0
                    if not writeQueue.empty():
                        writeObj = writeQueue.get(False)
                        await writehandler(writeObj[0],writeObj[1])
    
                    for d in deviceList:
                        d.publishDiagnostics()
                    anyAct=False

                    for p in pollers:
                        if p.disabled is not True:
                            anyAct=True

                    if not anyAct:
                        time.sleep(0.010)
                        for p in pollers:
                            if p.disabled == True:
                                p.disabled = False
                                p.failcounter = 0
                                if verbosity>=1:
                                    print("Reactivated poller "+p.topic+" with Slave-ID "+str(p.slaveid)+ " and functioncode "+str(p.functioncode)+".")
                except Exception as e:
                    if verbosity>=1:
                        print("Error: "+str(e)+" when polling or publishing, trying again...")
    await master.close()
    #adder.removeAll(referenceList)
    sys.exit(1)
