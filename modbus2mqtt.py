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

import addToHomeAssistant

from pymodbus.pdu import ModbusRequest
from pymodbus.client.sync import ModbusSerialClient as SerialModbusClient
from pymodbus.client.sync import ModbusTcpClient as TCPModbusClient
from pymodbus.transaction import ModbusRtuFramer

version="0.3"
    
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
parser.add_argument('--autoremove',action='store_true',help='Automatically remove poller if modbus communication has failed three times.')
parser.add_argument('--add-to-homeassistant',action='store_true',help='Add devices to Home Assistant using Home Assistant\'s MQTT-Discovery')
parser.add_argument('--set-loop-break',default='0.01',type=float, help='Set pause in main polling loop. Defaults to 10ms.')


args=parser.parse_args()
verbosity=args.verbosity
addToHass=False
addToHass=args.add_to_homeassistant


class Control:
    def __init__(self):
        self.runLoop = True
    def stopLoop(self):
        self.runLoop = False

control = Control()

globaltopic=args.mqtt_topic

if not globaltopic.endswith("/"):
    globaltopic+="/"

if verbosity>=0:
    print('Starting spiciermodbus2mqtt V%s with topic prefix \"%s\"' %(version, globaltopic))

master=None

def signal_handler(signal, frame):
        print('Exiting ' + sys.argv[0])
        control.stopLoop()
signal.signal(signal.SIGINT, signal_handler)

deviceList=[]
referenceList=[]


class Device:
    def __init__(self,name,slaveid):
        self.name=name
        self.occupiedTopics=[]
        self.writableReferences=[]
        self.slaveid=slaveid
        if verbosity>=2:
            print('Added new device \"'+self.name+'\"')


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
            print("Added new Poller "+str(self.topic)+","+str(self.functioncode)+","+str(self.dataType)+","+str(self.reference)+","+str(self.size)+",")


    def failCount(self,failed):
        if not failed:
            self.failcounter=0
            if not self.connected:
                self.connected = True
                mqc.publish(globaltopic + self.topic +"/connected", "True", qos=1, retain=True)
        else:
            if self.failcounter==3:
                if args.autoremove:
                    self.disabled=True
                    print("Poller "+self.topic+" with Slave-ID "+str(self.slaveid)+ " and functioncode "+str(self.functioncode)+" disabled due to the above error.")
                self.failcounter=4
                self.connected = False
                mqc.publish(globaltopic + self.topic +"/connected", "False", qos=1, retain=True)
                
            else:
                if self.failcounter<3:
                    self.failcounter+=1


    def poll(self):
            result = None
            if master.is_socket_open()==True:
                failed = False
                try:
                    if self.functioncode == 3:
                        result = master.read_holding_registers(self.reference, self.size, unit=self.slaveid)
                        if result.function_code < 0x80:
                            data = result.registers
                        else:
                            failed = True
                    if self.functioncode == 1:
                        result = master.read_coils(self.reference, self.size, unit=self.slaveid)
                        if result.function_code < 0x80:
                            data = result.bits
                        else:
                            failed = True

                    if self.functioncode == 2:
                        result = master.read_discrete_inputs(self.reference, self.size, unit=self.slaveid)
                        if result.function_code < 0x80:
                            data = result.bits
                        else:
                            failed = True
                    if self.functioncode == 4:
                        result = master.read_input_registers(self.reference, self.size, unit=self.slaveid)
                        if result.function_code < 0x80:
                            data = result.registers
                        else:
                            failed = True
                    if not failed:
                        if verbosity>=4:
                            print("Read MODBUS, FC:"+str(self.functioncode)+", DataType:"+str(self.dataType)+", ref:"+str(self.reference)+", Qty:"+str(self.size)+", SI:"+str(self.slaveid))
                            print("Read MODBUS, DATA:"+str(data))
                        for ref in self.readableReferences:
                            ref.checkPublish(data,self.topic)
                    else:
                        if verbosity>=1:
                            print("Slave device "+str(self.slaveid)+" responded with error code: "+str(result.function_code))
                except:
                    failed = True
                    if verbosity>=1:
                        print("Error talking to slave device:"+str(self.slaveid)+", trying again...")
                self.failCount(failed)
            else:
                if master.connect():
                    if verbosity >= 1:
                        print("MODBUS connected successfully")
                else:
                    for p in pollers:
                        p.failed=True
                        if p.failcounter<3:
                            p.failcounter=3
                        p.failCount(p.failed)
                    if verbosity >= 1:
                        print("MODBUS connection error, trying again...")

    def checkPoll(self):
        if time.clock_gettime(0) >= self.next_due and not self.disabled:
            self.poll()
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

class dataTypes:
    def __init__(self,conf):
        if conf is None or conf == "uint16" or conf == "":
            self.regAmount=1          
            self.parse=self.parseuint16
            self.combine=self.combineuint16
        elif conf.startswith("string"):
            try:
                length = int(conf[6:9])
            except:
                length = 2
            if length > 100:
                print("Data type string: length too long")
                length = 100
            if  math.fmod(length,2) != 0:
                length=length-1
                print("Data type string: length must be divisible by 2")
            self.parse=self.parseString
            self.combine=self.combineString
            self.stringLength=length
            self.regAmount=int(length/2)
        #elif conf == "int32LE":
           # self.parse=self.parseint32LE
           # self.combine=self.combineint32LE
           # self.regAmount=2          
        #elif conf == "int32BE":
         #   self.regAmount=2
          #  self.parse=self.parseint32BE
           # self.combine=self.combineint32BE
        elif conf == "int16":
            self.regAmount=1         
            self.parse=self.parseint16
            self.combine=self.combineint16
        elif conf == "uint32LE":
            self.regAmount=2          
            self.parse=self.parseuint32LE
            self.combine=self.combineuint32LE
        elif conf == "uint32BE":
            self.regAmount=2          
            self.parse=self.parseuint32BE
            self.combine=self.combineuint32BE
        elif conf == "bool":
            self.regAmount=1         
            self.parse=self.parsebool
            self.combine=self.combinebool
    
    def parsebool(self,msg):
        return msg
    def combinebool(self,val):
        return str(val[0])

    def parseString(self,msg):
        out=[]
        if len(msg)<=self.stringLength:
            for x in range(1,len(msg)+1):
                if math.fmod(x,2)>0:
                    out.append(ord(msg[x-1])<<8)
                else:
                    pass
                    out[int(x/2-1)]+=ord(msg[x-1])
        else:
            out = None
        return out
    def combineString(self,val):
        out=""
        for x in val:
            out+=chr(x>>8)
            out+=chr(x&0x00FF)
            print(val)
        return out

    def parseint32LE(self,msg):
        pass
    def combineint32LE(self,val):
        pass
    
    def parseint32BE(self,msg):
        pass
    def combineint32BE(self,val):
        pass


    def parseint16(self,msg):
        try:
            value=int(msg)
            if value > 32767 or value < -32768:
                out = None
            else:
                out = value&0xFFFF
        except:
            out=None
        return out
    def combineint16(self,val):
        if (val[0] & 0x8000) > 0:
            out = -((~val[0] & 0x7FFF)+1)
        else:
            out = val[0]
        return str(out)


    def parseuint32LE(self,msg):
        try:
            value=int(msg)
            if value > 4294967295 or value < 0:
                out = None
            else:
                out=[int(value>>16),int(value&0x0000FFFF)]
        except:
            out=None
        return out
    def combineuint32LE(self,val):
        out = val[0]*65536 + val[1]
        return str(out)


    def parseuint32BE(self,msg):
        try:
            value=int(msg)
            if value > 4294967295 or value < 0:
                out = None
            else:
                out=[int(value&0x0000FFFF),int(value>>16)]
        except:
            out=None
        return out
    def combineuint32BE(self,val):
        out = val[0] + val[1]*65536
        return str(out)
    
    def parseuint16(self,msg):
        try:
            value=int(msg)
            if value > 65535 or value < 0:
                value = None
        except:
            value=None
        return value
    def combineuint16(self,val):
        return str(val[0])


class Reference:
    def __init__(self,topic,reference,dtype,rw,poller):
        self.topic=topic
        self.reference=int(reference)
        self.lastval=None
        self.rw=rw
        self.relativeReference=None
        self.writefunctioncode=None
        self.device=None
        self.poller=poller
        self.dtype=None
        if self.poller.functioncode == 1:
            self.dtype=dataTypes("bool")
            
        elif self.poller.functioncode == 2:
            self.dtype=dataTypes("bool")
        else:
            self.dtype=dataTypes(dtype)
        self.length=self.dtype.regAmount

    def checkSanity(self,reference,size):
        if self.reference in range(reference,size+reference):
            self.relativeReference=self.reference-reference
            return True

    def checkPublish(self,result,topic):
        # Only publish messages after the initial connection has been made. If it became disconnected then the offline buffer will store messages,
        # but only after the intial connection was made.
        if mqc.initial_connection_made == True:
            val = result[self.relativeReference:(self.length+self.relativeReference)]
            if self.lastval != val:
                self.lastval= val
                try:
                    publish_result = mqc.publish(globaltopic+self.device.name+"/state/"+self.topic,self.dtype.combine(self.lastval),qos=1,retain=True)
                    if verbosity>=4:
                        print("published MQTT topic: " + str(self.device.name+"/state/"+self.topic)+" value: " + str(self.dtype.combine(self.lastval))+" RC:"+str(publish_result.rc))
                except:
                    if verbosity>=1:
                        print("Error publishing MQTT topic: " + str(self.device.name+"/state/"+self.topic)+"value: " + str(self.dtype.combine(self.lastval)))

        
pollers=[]

# type, topic, slaveid,  ref,           size, functioncode, rate
# type, topic, reference, rw, interpretation,      scaling,

# Now let's read the config file
with open(args.config,"r") as csvfile:
    csvfile.seek(0)
    reader=csv.DictReader(csvfile)
    currentPoller=None
    for row in reader:
        if row["type"]=="poller" or row["type"]=="poll":
            if row["col5"] == "holding_register":
                functioncode = 3
                dataType="int16"
            if row["col5"] == "coil":
                functioncode = 1
                dataType="bool"
            if row["col5"] == "input_register":
                functioncode = 4
                dataType="int16"
            if row["col5"] == "input_status":
                functioncode = 2
                dataType="bool"
            rate = float(row["col6"])
            slaveid = int(row["col2"])
            reference = int(row["col3"])
            size = int(row["col4"])
            currentPoller = Poller(row["topic"],rate,slaveid,functioncode,reference,size,dataType)
            pollers.append(currentPoller)
            continue
        elif row["type"]=="reference" or row["type"]=="ref":
            currentPoller.addReference(Reference(row["topic"],row["col2"],row["col4"],row["col3"],currentPoller))

def messagehandler(mqc,userdata,msg):
    if True:
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
        if myRef.writefunctioncode == 5:
            value = None
            if payload == 'True' or payload == 'true' or payload == '1' or payload == 'TRUE':
                value = True
            if payload == 'False' or payload == 'false' or payload == '0' or payload == 'FALSE':
                value = False
            if value != None:
                    result = master.write_coil(int(myRef.reference),value,unit=int(myRef.device.slaveid))
                    try:
                        if result.function_code < 0x80:
                            if verbosity>=3:
                                print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" successful.")
                        else:
                            if verbosity>=1:
                                print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" FAILED! (Devices responded with errorcode. Maybe bad configuration?)")
            
                    except NameError:
                        if verbosity>=1:
                            print("Error writing to slave device "+str(myDevice.slaveid)+" (maybe CRC error or timeout)")
            else:
                if verbosity >= 1:
                    print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" not possible. Given value is not \"True\" or \"False\".")


        if myRef.writefunctioncode == 6:
            value = myRef.dtype.parse(str(payload))
            if value is not None:
                result = master.write_registers(int(myRef.reference),value,unit=myRef.device.slaveid)
                try:
                    if result.function_code < 0x80:
                        if verbosity>=3:
                            print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" successful.")
                    else:
                        if verbosity>=1:
                            print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" FAILED! (Devices responded with errorcode. Maybe bad configuration?)")
                except NameError:
                    if verbosity >= 1:
                        print("Error writing to slave device "+str(myDevice.slaveid)+" (maybe CRC error or timeout)")
            else:
                if verbosity >= 1:
                    print("Writing to device "+str(myDevice.name)+", Slave-ID="+str(myDevice.slaveid)+" at Reference="+str(myRef.reference)+" using function code "+str(myRef.writefunctioncode)+" not possible. Value does not fulfill criteria.")
        
def connecthandler(mqc,userdata,flags,rc):
    if rc == 0:
        mqc.initial_connection_made = True
        if verbosity>=2:
            print("MQTT Broker connected succesfully: " + args.mqtt_host + ":" + str(mqtt_port))
        mqc.subscribe(globaltopic + "+/set/+")
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



if True:
#Setup MODBUS Master
    if args.rtu:

        if args.rtu_parity == "none":
            parity = "N"
        if args.rtu_parity == "odd":
            parity = "O"
        if args.rtu_parity == "even":
            parity = "E"

        master = SerialModbusClient(method="rtu", port=args.rtu, stopbits = 1, bytesize = 8, parity = parity, baudrate = int(args.rtu_baud), timeout=args.set_modbus_timeout)

    elif args.tcp:
        master = TCPModbusClient(args.tcp, args.tcp_port,client_id="foo123", clean_session=False)
    else:
        print("You must specify a modbus access method, either --rtu or --tcp")
        sys.exit(1)

#Setup MQTT Broker

    mqtt_port = args.mqtt_port

    if mqtt_port is None:
        if args.mqtt_use_tls:
            mqtt_port = 8883
        else:
            mqtt_port = 1883

    clientid=globaltopic + "-" + str(time.time())
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



#Main Loop
modbus_connected = False
while control.runLoop:
    if not modbus_connected:
        print("Connecting to MODBUS...")
        modbus_connected = master.connect()
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
                print("MODBUS connection error, trying again...")

    if not mqc.initial_connection_attempted:
       try:
            print("Connecting to MQTT Broker: " + args.mqtt_host + ":" + str(mqtt_port) + "...")
            mqc.connect(args.mqtt_host, mqtt_port, 60)
            mqc.initial_connection_attempted = True #Once we have connected the mqc loop will take care of reconnections.
            mqc.loop_start()
            #Setup HomeAssistant
            if(addToHass):
                adder=addToHomeAssistant.HassConnector(mqc,globaltopic,verbosity>=1)
                adder.addAll(referenceList)
            if verbosity >= 1:
                print("MQTT Loop started")
       except:
            if verbosity>=1:
              print("Socket Error connecting to MQTT broker: " + args.mqtt_host + ":" + str(mqtt_port) + ", check LAN/Internet connection, trying again...")

    if mqc.initial_connection_made: #Don't start polling unless the initial connection to MQTT has been made, no offline MQTT storage will be available until then.
        if modbus_connected:
            try:
                for p in pollers:
                    p.checkPoll()
            except:
                if verbosity>=1:
                    print("Exception Error when polling or publishing, trying again...")

    time.sleep(args.set_loop_break)

master.close()
#adder.removeAll(referenceList)
sys.exit(1)

