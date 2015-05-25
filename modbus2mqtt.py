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
import json
import socket
import paho.mqtt.client as mqtt
import serial
import io
import csv

import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu

version="0.1"

parser = argparse.ArgumentParser(description='Bridge between ModBus and MQTT')
parser.add_argument('--mqtt-host', default='localhost', help='MQTT server address. Defaults to "localhost"')
parser.add_argument('--mqtt-port', default='1883', type=int, help='MQTT server port. Defaults to 1883')
parser.add_argument('--mqtt-topic', default='modbus/', help='Topic prefix to be used for subscribing/publishing. Defaults to "modbus/"')
parser.add_argument('--rtu', help='pyserial URL (or port name) for RTU serial port')
parser.add_argument('--rtu-baud', default='2400', type=int, help='Baud rate for serial port. Defaults to 2400')
parser.add_argument('--registers', required=True, help='Register specification file. Must be specified')
parser.add_argument('--log', help='set log level to the specified value. Defaults to WARNING. Try DEBUG for maximum detail')
parser.add_argument('--syslog', action='store_true', help='enable logging to syslog')
args=parser.parse_args()

if args.log:
    logging.getLogger().setLevel(args.log)
if args.syslog:
    logging.getLogger().addHandler(logging.handlers.SysLogHandler())

topic=args.mqtt_topic
if not topic.endswith("/"):
	topic+="/"

logging.info('Starting modbus2mqtt V%s with topic prefix \"%s\"' %(version, topic))

class Register:
	def __init__(self,topic,frequency,slaveid,functioncode,register,size,format):
		self.topic=topic
		self.frequency=int(frequency)
		self.slaveid=int(slaveid)
		self.functioncode=int(functioncode)
		self.register=int(register)
		self.size=int(size)
		self.format=format
		self.next_due=0
		self.lastval=None

	def checkpoll(self):
		if self.next_due<time.time():
			self.poll()
			self.next_due=time.time()+self.frequency
			
	def poll(self):
		try:
			res=master.execute(self.slaveid,self.functioncode,self.register,self.size,data_format=self.format)
			if res[0]!=self.lastval:
				self.lastval=res[0]
				fulltopic=topic+"status/"+self.topic
				mqc.publish(fulltopic,self.lastval,qos=0,retain=True)

		except modbus_tk.modbus.ModbusError as exc:
			logging.error("Error reading "+self.topic+": Slave returned %s - %s", exc, exc.get_exception_code())
		except Exception as exc:
			logging.error("Error reading "+self.topic+": %s", exc)

registers=[]

# Now lets read the register definition
with open(args.registers,"r") as csvfile:
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

logging.info('Read %u valid register definitions from \"%s\"' %(len(registers), args.registers))

def connecthandler(mqc,userdata,rc):
    logging.info("Connected to MQTT broker with rc=%d" % (rc))

def disconnecthandler(mqc,userdata,rc):
    logging.warning("Disconnected from MQTT broker with rc=%d" % (rc))

mqc=mqtt.Client()
mqc.on_connect=connecthandler
mqc.on_disconnect=disconnecthandler
mqc.will_set(topic+"connected",0,qos=2,retain=True)
mqc.connect(args.mqtt_host,args.mqtt_port,60)
mqc.publish(topic+"connected",1,qos=1,retain=True)
mqc.loop_start()

if args.rtu:
	master=modbus_rtu.RtuMaster(serial.serial_for_url(args.rtu,baudrate=args.rtu_baud))
	master.set_timeout(5.0)
	master.set_verbose(True)

mqc.publish(topic+"connected",2,qos=1,retain=True)

while True:
	for r in registers:
		r.checkpoll()
	time.sleep(1)
	