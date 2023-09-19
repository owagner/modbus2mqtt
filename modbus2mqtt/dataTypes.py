import math
import struct

class DataTypes:
    def parsebool(refobj,payload):
        if payload == 'True' or payload == 'true' or payload == '1' or payload == 'TRUE':
            value = True
        elif payload == 'False' or payload == 'false' or payload == '0' or payload == 'FALSE':
            value = False
        else:
            value = None
        return value

    def combinebool(refobj,val):
        try:
            len(val)
            return bool(val[0])
        except:
            return bool(val)

    def parseString(refobj,msg):
        out=[]
        if len(msg)<=refobj.stringLength:
            for x in range(1,len(msg)+1):
                if math.fmod(x,2)>0:
                    out.append(ord(msg[x-1])<<8)
                else:
                    pass
                    out[int(x/2-1)]+=ord(msg[x-1])
        else:
            out = None
        return out
    def combineString(refobj,val):
        out=""
        for x in val:
            out+=chr(x>>8)
            out+=chr(x&0x00FF)
        return out

    def parseint16(refobj,msg):
        try:
            value=int(msg)
            if value > 32767 or value < -32768:
                out = None
            else:
                out = value&0xFFFF
        except:
            out=None
        return out
    def combineint16(refobj,val):
        try:
            len(val)
            myval=val[0]
        except:
            myval=val

        if (myval & 0x8000) > 0:
            out = -((~myval & 0x7FFF)+1)
        else:
            out = myval
        return out

    def parseuint32LE(refobj,msg):
        try:
            value=int(msg)
            if value > 4294967295 or value < 0:
                out = None
            else:
                out=[int(value>>16),int(value&0x0000FFFF)]
        except:
            out=None
        return out
    def combineuint32LE(refobj,val):
        out = val[0]*65536 + val[1]
        return out

    def parseuint32BE(refobj,msg):
        try:
            value=int(msg)
            if value > 4294967295 or value < 0:
                out = None
            else:
                out=[int(value&0x0000FFFF),int(value>>16)]
        except:
            out=None
        return out
    def combineuint32BE(refobj,val):
        out = val[0] + val[1]*65536
        return out

    def parseint32LE(refobj,msg):
        #try:
        #    value=int(msg)
        #    value = int.from_bytes(value.to_bytes(4, 'little', signed=False), 'little', signed=True)
        #except:
        #    out=None
        #return out
        return None
    def combineint32LE(refobj,val):
        out = val[0]*65536 + val[1]
        out = int.from_bytes(out.to_bytes(4, 'little', signed=False), 'little', signed=True)
        return out

    def parseint32BE(refobj,msg):
        #try:
        #    value=int(msg)
        #    value = int.from_bytes(value.to_bytes(4, 'big', signed=False), 'big', signed=True)
        #except:
        #    out=None
        #return out
        return None
    def combineint32BE(refobj,val):
        out = val[0] + val[1]*65536
        out = int.from_bytes(out.to_bytes(4, 'big', signed=False), 'big', signed=True)
        return out

    def parseuint16(refobj,msg):
        try:
            value=int(msg)
            if value > 65535 or value < 0:
                value = None
        except:
            value=None
        return value
    def combineuint16(refobj,val):
        try:
            len(val)
            return val[0]
        except:
            return val

    def parsefloat32LE(refobj,msg):
        try:
            out=None
            #value=int(msg)
            #if value > 4294967295 or value < 0:
            #    out = None
            #else:
            #    out=[int(value&0x0000FFFF),int(value>>16)]
        except:
            out=None
        return out
    def combinefloat32LE(refobj,val):
        out = str(struct.unpack('=f', struct.pack('=I',int(val[0])<<16|int(val[1])))[0])
        return out

    def parsefloat32BE(refobj,msg):
        try:
            out=None
            #value=int(msg)
            #if value > 4294967295 or value < 0:
            #    out = None
            #else:
            #    out=[int(value&0x0000FFFF),int(value>>16)]
        except:
            out=None
        return out
    def combinefloat32BE(refobj,val):
        out = str(struct.unpack('=f', struct.pack('=I',int(val[1])<<16|int(val[0])))[0])
        return out
    def parseDataType(refobj,conf):
        if conf is None or conf == "uint16" or conf == "":
            refobj.regAmount=1
            refobj.parse=DataTypes.parseuint16
            refobj.combine=DataTypes.combineuint16
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
            refobj.parse=DataTypes.parseString
            refobj.combine=DataTypes.combineString
            refobj.stringLength=length
            refobj.regAmount=int(length/2)
        elif conf == "int32LE":
            refobj.parse=DataTypes.parseint32LE
            refobj.combine=DataTypes.combineint32LE
            refobj.regAmount=2
        elif conf == "int32BE":
            refobj.regAmount=2
            refobj.parse=DataTypes.parseint32BE
            refobj.combine=DataTypes.combineint32BE
        elif conf == "int16":
            refobj.regAmount=1
            refobj.parse=DataTypes.parseint16
            refobj.combine=DataTypes.combineint16
        elif conf == "uint32LE":
            refobj.regAmount=2
            refobj.parse=DataTypes.parseuint32LE
            refobj.combine=DataTypes.combineuint32LE
        elif conf == "uint32BE":
            refobj.regAmount=2
            refobj.parse=DataTypes.parseuint32BE
            refobj.combine=DataTypes.combineuint32BE
        elif conf == "bool":
            refobj.regAmount=1
            refobj.parse=DataTypes.parsebool
            refobj.combine=DataTypes.combinebool
        elif conf == "float32LE":
            refobj.regAmount=2
            refobj.parse=DataTypes.parsefloat32LE
            refobj.combine=DataTypes.combinefloat32LE
        elif conf == "float32BE":
           refobj.regAmount=2
           refobj.parse=DataTypes.parsefloat32BE
           refobj.combine=DataTypes.combinefloat32BE