import serial, time

ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=2)
time.sleep(0.5)
ser.flushInput()

for cmd in ['AT', 'AT+CPIN?', 'AT+CSQ', 'AT+CREG?']:
    ser.write((cmd + '\r').encode())
    time.sleep(1)
    resp = ser.read_all()
    print(f'{cmd} → {resp.decode("utf-8", errors="replace").strip()}')

ser.close()