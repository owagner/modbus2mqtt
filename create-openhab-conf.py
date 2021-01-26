#!/usr/bin/env python3
import argparse
import csv

class Thing:
    def __init__(self,pollerTopic,adr):
        self.pollerTopic=pollerTopic
        self.channels=[]
        self.adr=adr
    
    def addChannel(self,chan):
        self.channels.append(chan)
        
class Channel:
    def __init__(self,thing,refname,chantype,rw,interpretation):
        self.refname=refname
        self.map=None
        self.commandTopic=None
        self.thing=thing
        self.chantype=None
        if chantype == "register" and "r" in rw and not "w" in rw:
            self.chantype = "number"
            self.map=""
        elif chantype == "register" and "w" in rw:
            self.chantype = "number"
            self.map=""
            self.commandTopic=globaltopic+"/"+self.thing.pollerTopic+"/set/"+self.refname
        elif chantype == "coil" and "w" in rw:
            self.chantype = "switch"
            self.commandTopic=globaltopic+"/"+self.thing.pollerTopic+"/set/"+self.refname
            self.map=", on=\"True\", off=\"False\""
        elif chantype == "coil" and not "w" in rw:
            self.chantype = "contact"
            self.map=", on=\"True\", off=\"False\""
        elif chantype == "input_status" and "r" in rw:
            self.chantype = "contact"
            self.map=", on=\"True\", off=\"False\""
        self.rw=rw
        self.stateTopic=globaltopic+"/"+self.thing.pollerTopic+"/state/"+self.refname
        

thinglist=[]

def getconf(x):
    if len(x.channels)<1:
        return ""
    outstring=""
    outstring+="Thing mqtt:topic:"+x.pollerTopic+" \""+x.pollerTopic+"\" ("+brokerstring+") {\n"
    outstring+="    Channels:\n"
    outstring+="        Type contact : "+x.pollerTopic+"_connected [ stateTopic=\"" + globaltopic+"/"+x.pollerTopic+"/connected\", on=\"True\", off=\"False\" ]\n"
    for y in x.channels:
        outstring+="        Type "+y.chantype+" : "+y.refname+" [ stateTopic=\""+y.stateTopic+"\""
        if y.commandTopic:
            outstring+=", commandTopic=\""+y.commandTopic+"\""
        outstring+=y.map
        outstring+=" ]\n"
    outstring+="}\n\n"
    return outstring

def getitemconf(x):
    if len(x.channels)<1:
        return ""
    outstring=""
    outstring+="Contact "+x.pollerTopic+"_"+x.pollerTopic+"_connected"+" \""+x.pollerTopic+"_"+x.pollerTopic+"_connected\" "
    outstring+="{ channel=\"mqtt:topic:"+x.pollerTopic+":"+x.pollerTopic+"_connected\" }\n"
    for y in x.channels:
        outstring+=y.chantype.capitalize()+" "+x.pollerTopic+"_"+y.refname+" \""+x.pollerTopic+"_"+y.refname+"\" "
        outstring+="{ channel=\"mqtt:topic:"+x.pollerTopic+":"+y.refname+"\" }"
        outstring+="\n"
    return outstring



parser = argparse.ArgumentParser(description='Bridge between ModBus and MQTT')
parser.add_argument('globaltopic', help='from argument of modbus2mqtt.py, usually modbus')
parser.add_argument('brokerstring', help='Broker string for ex. mqtt:broker:2c8f40c6')
parser.add_argument('config', help='Configuration file. Required!')

args=parser.parse_args()
globaltopic=args.globaltopic
brokerstring=args.brokerstring

verbosity = 10

with open(args.config,"r") as csvfile:
    csvfile.seek(0)
    reader=csv.DictReader(csvfile)
    currentPoller=None
    pollerTopic=None
    pollerType=None
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
                if size>2000:
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
            pollerType = row["col5"]
            pollerTopic = row["topic"]
            currentPoller = None
            for x in thinglist:
                if x.pollerTopic == pollerTopic:
                    currentPoller = x
            if currentPoller is None:
                currentPoller = Thing(pollerTopic,slaveid)
                thinglist.append(currentPoller)
            continue
        elif row["type"]=="reference" or row["type"]=="ref":
            if currentPoller is not None:
                if pollerType == "coil":
                    chan=Channel(currentPoller,row["topic"],"coil",row["col3"],"") 
                    currentPoller.channels.append(chan)
                elif pollerType == "holding_register":
                    chan=Channel(currentPoller,row["topic"],"register",row["col3"],"") 
                    currentPoller.channels.append(chan)
                elif pollerType == "input_register":
                    chan=Channel(currentPoller,row["topic"],"register","r","") 
                    currentPoller.channels.append(chan)
                elif pollerType == "input_status":
                    chan=Channel(currentPoller,row["topic"],"input_status","r","") 
                    currentPoller.channels.append(chan)
            else:
                print("No poller for reference "+row["topic"]+".")

outstring = ""
for x in thinglist:
    outfile = open(x.pollerTopic+".things","w+")
    outfile.write(getconf(x))
    outfile.close()
    outfile = open(x.pollerTopic+".items","w+")
    outfile.write(getitemconf(x))
    outfile.close()
