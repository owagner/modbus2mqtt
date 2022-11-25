FROM python:alpine

WORKDIR /app

COPY modbus2mqtt.py ./
COPY modbus2mqtt modbus2mqtt/

RUN mkdir -p /app/conf/

# upgrade pip to avoid warnings during the docker build
RUN pip install --root-user-action=ignore --upgrade pip

# ensure we have the version 2.5.3 of pymodbus installed
RUN pip install --root-user-action=ignore --no-cache-dir pymodbus==2.5.3
RUN pip install --root-user-action=ignore --no-cache-dir paho-mqtt

ENTRYPOINT [ "python", "-u", "./modbus2mqtt.py", "--config", "/app/conf/modbus2mqtt.csv" ]
