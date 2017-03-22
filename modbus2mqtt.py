#
# modbus2mqtt - Modbus master with MQTT publishing
#
# Written and (C) 2015 by Oliver Wagner <owagner@tellerulam.com>
# Provided under the terms of the MIT license
#
# Requires:
# - Eclipse Paho for Python - http://www.eclipse.org/paho/clients/python/
# - modbus-tk for Modbus communication - https://github.com/ljean/modbus-tk/
#

import argparse
import logging
import logging.handlers
import time
import socket
import paho.mqtt.client as mqtt
import serial
import io
import sys
import csv
import signal

#TODO just needed for modbus_tk.modbus.ModbusError -> replace by a more concrete import
import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
from modbus_tk import modbus_tcp

version="0.6"

class Register:
    def __init__(self,topic,frequency,slaveid,functioncode,register,size,format):
        self.topic=topic
        self.frequency=int(frequency)
        self.slaveid=int(slaveid)
        self.functioncode=int(functioncode)
        self.register=int(register)
        self.size=int(size)
        self.format=format.split(":",2)
        self.next_due=0
        self.lastval=None
        self.last = None

    def pollNecessary(self):
        return self.next_due<time.time()

    def setPollSuccessful(self):
        self.last = time.time()
        self.next_due=time.time()+self.frequency

class ModbusHandler(object):
    master = None
    def __init__(self, args):
        self.force = args.force

        if args.rtu:
            self.master=modbus_rtu.RtuMaster(serial.serial_for_url(args.rtu,baudrate=args.rtu_baud,parity=args.rtu_parity[0].upper()))
        elif args.tcp:
            self.master=modbus_tcp.TcpMaster(args.tcp,args.tcp_port)
        else:
            logging.error("You must specify a modbus access method, either --rtu or --tcp")
            sys.exit(1)
        logging.debug("master is: %s", self.master)

        self.master.set_verbose(True)
        self.master.set_timeout(5.0)

    def getModbusMaster(self):
        return self.master

    def pollRegister(self, register):
        polledValue = None
        r = None
        try:
            logging.debug("Arguments:%s,%s,%s,%s,%s" % (register.slaveid,register.functioncode,register.register,register.size,register.format[0]))
            res=self.master.execute(register.slaveid,register.functioncode,register.register,register.size,data_format=register.format[0])

            logging.debug("res: %s", res)
            r=res[0]
            if register.format[1]:
                r=register.format[1] % r

            register.setPollSuccessful()
        except modbus_tk.modbus.ModbusError as exc:
            logging.error("Error reading from slave id %s, Slave returned %s - %s" % (register.slaveid, exc, exc.get_exception_code()))
        except Exception as exc:
            logging.error("Error reading from slave id %s, functioncode:%d, regAddress:%d. Error:%s" % (register.slaveid, register.functioncode, register.register, exc))
            logging.error("Arguments:%s,%s,%s,%s,%s" % (register.slaveid,register.functioncode,register.register,register.size,register.format[0]))

        if r and (r!=register.lastval or (self.force and (time.time() - register.last) > int(self.force))):
            register.lastval=r
            polledValue = register.lastval

        return polledValue

class MqttHandler(object):
    topic = ""
    mqc = None
    _on_message_handler = None

    def __init__(self, args):
        self._mqtt_host = args.mqtt_host
        self._mqtt_port  = args.mqtt_port
        topic = args.mqtt_topic
        topic+="/" if not topic.endswith("/") else ""
        self.topic = topic

        logging.debug('Starting mqttHanlder topic prefix \"%s\"' %(self.topic))

        clientid=args.clientid + "-" + str(time.time())
        logging.debug("topic:%s, clientid:%s" % (self.topic, clientid))
        #@see http://stackoverflow.com/questions/15331726/how-does-the-functools-partial-work-in-python
        self.mqc=mqtt.Client(client_id=clientid)
        self.mqc.on_connect=    lambda mqc,userdata,rc : self.connecthandler(mqc,userdata,rc)
        self.mqc.on_disconnect= lambda mqc,userdata,rc : self.disconnecthandler(mqc,userdata,rc)
        self.mqc.on_message=    lambda mqc,userdata,rc : self._on_message_handler(mqc,userdata,rc)
        self.mqc.will_set(self.topic+"disconnecting",0,qos=2,retain=True)
        self.mqc.disconnected =True

    def connect(self):
        #the following must not be in the __init__ in order get the message handler instanced
        self.mqc.connect(self._mqtt_host, self._mqtt_port, 60)
        self.mqc.loop_start()

    def registerMessageHandler(self, on_message_handler):
        self._on_message_handler = on_message_handler

    def connecthandler(self, mqc,userdata,rc):
        logging.info("Connected to MQTT broker with rc=%d" % (rc))
        mqc.subscribe(self.topic+"set/+/"+str(cst.WRITE_SINGLE_REGISTER)+"/+")
        mqc.subscribe(self.topic+"set/+/"+str(cst.WRITE_SINGLE_COIL)+"/+")
        mqc.publish(self.topic+"connected",2,qos=1,retain=True)

    def disconnecthandler(self, mqc,userdata,rc):
        logging.warning("Disconnected from MQTT broker with rc=%d" % (rc))

class Modbus2MQTT(object):
    def __init__(self, modbusHandler, mqttHandler, args):
        self.modbusHandler = modbusHandler
        self.mqttHandler = mqttHandler
        self.mqttHandler.registerMessageHandler(self.messagehandler)

        self.registers = self.parseRegisterFile(args.registers)

    # Async message receiver
    def messagehandler(self, mqc,userdata,msg):
        master = self.modbusHandler.getModbusMaster()

        logging.debug("called messagehandler")
        try:
            (prefix,function,slaveid,functioncode,register) = msg.topic.split("/")
            if function != 'set':
                return
            if int(slaveid) not in range(0,255):
                logging.warning("on message - invalid slaveid " + msg.topic)
                return

            if not (int(register) >= 0 and int(register) < sys.maxint):
                logging.warning("on message - invalid register " + msg.topic)
                return

            if functioncode == str(cst.WRITE_SINGLE_COIL):
                logging.info("Writing single coil " + register)
            elif functioncode == str(cst.WRITE_SINGLE_REGISTER):
                logging.info("Writing single register " + register)
            else:
                logging.error("Error attempting to write - invalid function code " + msg.topic)
                return

            res=master.execute(int(slaveid),int(functioncode),int(register),output_value=int(msg.payload))

        except Exception as e:
            logging.error("Error on message " + msg.topic + " :" + str(e))

    def doPoll(self):
        for r in self.registers:
            toBePublished = None

            if r.pollNecessary():
                toBePublished = self.modbusHandler.pollRegister(r)
                logging.debug("tobePublished: %s" % toBePublished)
            if toBePublished:
                #TODO move to mqttHandler.publish(content)
                fulltopic = self.mqttHandler.topic+"status/"+r.topic
                logging.debug("going to publish register id: %d, to topic:%s" % (r.register, fulltopic))
                try:
                    self.mqttHandler.mqc.publish(fulltopic,toBePublished,qos=0,retain=True)
                except Exception as exc:
                    logging.error("Error writing to topic "+fulltopic+": %s", exc)

    def parseRegisterFile(self, filename):
        registers=[]

        # Now lets read the register definition
        with open(filename,"r") as csvfile:
            dialect=csv.Sniffer().sniff(csvfile.read(8192))
            csvfile.seek(0)
            defaultrow={"Size":1,"Format":">H","Frequency":60,"Slave":1,"FunctionCode":4}
            reader=csv.DictReader(csvfile,fieldnames=["Topic","Register","Size","Format","Frequency","Slave","FunctionCode"],dialect=dialect)
            for row in reader:
                # Skip header row
                if row["Frequency"]=="Frequency":
                    continue
                # Comment?
                if row["Topic"][0]=="#":
                    continue
                if row["Topic"]=="DEFAULT":
                    temp=dict((k,v) for k,v in row.iteritems() if v is not None and v!="")
                    defaultrow.update(temp)
                    continue
                freq=row["Frequency"]
                if freq is None or freq=="":
                    freq=defaultrow["Frequency"]
                slave=row["Slave"]
                if slave is None or slave=="":
                    slave=defaultrow["Slave"]
                fc=row["FunctionCode"]
                if fc is None or fc=="":
                    fc=defaultrow["FunctionCode"]
                fmt=row["Format"]
                if fmt is None or fmt=="":
                    fmt=defaultrow["Format"]
                size=row["Size"]
                if size is None or size=="":
                    size=defaultrow["Size"]
                r=Register(row["Topic"],freq,slave,fc,row["Register"],size,fmt)
                registers.append(r)

        logging.info('Read %u valid register definitions from \"%s\"' %(len(registers), filename))
        return registers


def parseArgs():
    parser = argparse.ArgumentParser(description='Bridge between ModBus and MQTT')
    parser.add_argument('--mqtt-host', default='localhost', help='MQTT server address. Defaults to "localhost"')
    parser.add_argument('--mqtt-port', default='1883', type=int, help='MQTT server port. Defaults to 1883')
    parser.add_argument('--mqtt-topic', default='modbus/', help='Topic prefix to be used for subscribing/publishing. Defaults to "modbus/"')
    parser.add_argument('--clientid', default='modbus2mqtt', help='Client ID prefix for MQTT connection')
    parser.add_argument('--rtu', help='pyserial URL (or port name) for RTU serial port')
    parser.add_argument('--rtu-baud', default='19200', type=int, help='Baud rate for serial port. Defaults to 19200')
    parser.add_argument('--rtu-parity', default='even', choices=['even','odd','none'], help='Parity for serial port. Defaults to even')
    parser.add_argument('--tcp', help='Act as a Modbus TCP master, connecting to host TCP')
    parser.add_argument('--tcp-port', default='502', type=int, help='Port for Modbus TCP. Defaults to 502')
    parser.add_argument('--registers', required=True, help='Register definition file. Required!')
    parser.add_argument('--log', help='set log level to the specified value. Defaults to WARNING. Use DEBUG for maximum detail')
    parser.add_argument('--syslog', action='store_true', help='enable logging to syslog')
    parser.add_argument('--force', default='0',type=int, help='publish values after "force" seconds since publish regardless of change. Defaults to 0 (change only)')
    return parser.parse_args()


def main():
    args = parseArgs()
    if args.log:
        logging.getLogger().setLevel(args.log)
    if args.syslog:
        logging.getLogger().addHandler(logging.handlers.SysLogHandler())
    else:
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    #TODO invoke modbusHandler.stop and mqttHandler.stop
    def signal_handler(signal, frame):
            print('Exiting ' + sys.argv[0])
            sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    logging.info('Starting modbus2mqtt V%s' %(version))
    modbusHandler = ModbusHandler(args)
    mqttHandler = MqttHandler(args)
    mqttHandler.connect()

    modbus2MQTT = Modbus2MQTT(modbusHandler, mqttHandler, args)
    while True:
        modbus2MQTT.doPoll()
        time.sleep(1)


if __name__ == "__main__":
    main()