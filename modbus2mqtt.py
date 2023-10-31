#!/usr/bin/env python
import asyncio
from  modbus2mqtt.modbus2mqtt import main
if __name__ == '__main__':
    asyncio.run(main(), debug=False)