# OHS Robot — MQTT Communication System

## Raspberry Pi Setup (run once)

```bash
# Mosquitto kurulum
sudo apt install mosquitto mosquitto-clients -y
sudo systemctl enable mosquitto

# Broker'ı hem LAN'dan hem WebSocket ile kullanılabilir yap
sudo tee /etc/mosquitto/conf.d/ohs_robot.conf > /dev/null <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true

listener 9001 0.0.0.0
protocol websockets
allow_anonymous true
EOF

sudo systemctl restart mosquitto

# SSH server
sudo systemctl enable ssh
sudo systemctl start ssh

# Log dizini
sudo mkdir -p /var/log/ohs_robot
sudo chown pi:pi /var/log/ohs_robot

# Bağımlılıklar
pip install -r requirements.txt

# Çalıştır
MQTT_BROKER_HOST=raspberrypi.local python main.py
```

## Ağdan Bağlanma

Robot ve web dashboard aynı Wi-Fi/LAN içindeyse broker olarak Raspberry Pi'nin
IP adresini veya mDNS adını kullanın:

```bash
export MQTT_BROKER_HOST=192.168.1.50
export MQTT_BROKER_PORT=1883
python main.py
```

Web dashboard için MQTT istemcisini WebSocket ile bağlayın:

```javascript
const client = mqtt.connect("ws://192.168.1.50:9001");
```

Eğer broker anonymous kapalıysa, robot için şunları ayarlayın:

```bash
export MQTT_USERNAME=ohs_robot
export MQTT_PASSWORD=strong-password
export MQTT_BROKER_HOST=192.168.1.50
python main.py
```

Dashboard tarafında aynı kullanıcı adı/parolayı verin veya broker'da anonymous erişimi açık bırakın.

## Manuel Test Komutları

```bash
# STOP komutu gönder
mosquitto_pub -h localhost -t ohs/robot/command \
  -m '{"cmd":"STOP","correlationId":"test-001","issuedBy":"test","timestamp":"2026-01-01T00:00:00Z"}'

# START komutu gönder
mosquitto_pub -h localhost -t ohs/robot/command \
  -m '{"cmd":"START","correlationId":"test-002","issuedBy":"test","timestamp":"2026-01-01T00:00:00Z"}'

# ALARM komutu gönder
mosquitto_pub -h localhost -t ohs/robot/command \
  -m '{"cmd":"ALARM","correlationId":"test-003","issuedBy":"test","timestamp":"2026-01-01T00:00:00Z"}'

# Tüm topic'leri dinle
mosquitto_sub -h localhost -t "ohs/#" -v
```

## Topic Haritası

| Topic                | Yön       | Modül  | Açıklama                      |
|----------------------|-----------|--------|-------------------------------|
| ohs/ppe/violation    | Publish   | MOD-01 | KKD ihlal tespiti             |
| ohs/env/hazard       | Publish   | MOD-02 | Çevresel tehlike okuması      |
| ohs/nav/position     | Publish   | MOD-03 | Anlık konum ve durum          |
| ohs/nav/waypoint     | Publish   | MOD-03 | Waypoint varış bildirimi      |
| ohs/robot/feedback   | Publish   | MOD-03 | Komut yanıtı                  |
| ohs/robot/command    | Subscribe | MOD-03 | START / STOP / ALARM komutları|
