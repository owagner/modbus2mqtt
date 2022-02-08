FROM python:alpine
WORKDIR /app
COPY modbus2mqtt.py ./
COPY modbus2mqtt modbus2mqtt/
RUN mkdir -p /app/conf/
RUN pip install --no-cache-dir pymodbus
RUN pip install --no-cache-dir paho-mqtt
ENTRYPOINT ["python","-u","./modbus2mqtt.py","--config","/app/conf/modbus2mqtt.csv"]
