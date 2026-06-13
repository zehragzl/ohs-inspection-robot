import os

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "10.185.186.191")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CLIENT_ID_PREFIX = "ohs_robot"

TOPIC_PPE_VIOLATION  = "ohs/ppe/violation"
TOPIC_ENV_HAZARD     = "ohs/env/hazard"
TOPIC_NAV_POSITION   = "ohs/nav/position"
TOPIC_NAV_WAYPOINT   = "ohs/nav/waypoint"
TOPIC_NAV_OBSTACLE   = "ohs/nav/obstacle"
TOPIC_ROBOT_FEEDBACK = "ohs/robot/feedback"
TOPIC_ROBOT_COMMAND  = "ohs/robot/command"

PPE_PUBLISH_INTERVAL = 3    # seconds
ENV_PUBLISH_INTERVAL = 2    # seconds
NAV_PUBLISH_INTERVAL = 8    # seconds

# Sabit derinlik (m) — tüm misyon boyunca değişmez
ROBOT_DEPTH_M = 0.60

# Robotun ileri hızı (m/s) — kalibre et!
# Ölçüm: robotu 1m ileri gönder, geçen saniyeyi ölç → hız = 1 / süre
ROBOT_SPEED_MPS = 0.8

# Seri port — None ise otomatik bulur (/dev/ttyUSB* veya /dev/ttyACM*)
ROBOT_PORT = None

# Waypoint planı: koridor boyunca düz ilerleme, y=0, derinlik sabit
#   x_m:       başlangıçtan toplam mesafe (blok × 0.46 m)
#   segment_m: bir önceki noktadan bu noktaya mesafe
#   dwell_ms:  bu noktada bekleme süresi (son nokta için 0)
#   label:     fiziksel konum adı (MQTT yayınında görünür)
WAYPOINTS = [
    {"id": 0, "label": "Z23",            "x_m":  0.00, "y_m": 0.0, "depth_m": 0.60, "segment_m": 0.00, "dwell_ms":    0},
    {"id": 1, "label": "Kolon",          "x_m":  4.83, "y_m": 0.0, "depth_m": 0.60, "segment_m": 3.00, "dwell_ms": 3000},
    {"id": 2, "label": "Otonom Lab",     "x_m":  9.89, "y_m": 0.0, "depth_m": 0.60, "segment_m": 3.40, "dwell_ms": 3000},
    {"id": 3, "label": "Sebil Önü",      "x_m": 13.11, "y_m": 0.0, "depth_m": 0.60, "segment_m": 2.00, "dwell_ms": 3000},
    {"id": 4, "label": "Priz",           "x_m": 18.63, "y_m": 0.0, "depth_m": 0.60, "segment_m": 2.76, "dwell_ms": 3000},
    {"id": 5, "label": "Mikroişlemciler","x_m": 22.77, "y_m": 0.0, "depth_m": 0.60, "segment_m": 2.07, "dwell_ms":    0},
]
DWELL_MS = 3000  # varsayılan bekleme (waypoint bazlı dwell_ms önceliklidir)

THRESHOLD_TEMP_C   = 60.0   # °C üstü tehlikeli
THRESHOLD_HUMIDITY = 85.0   # % üstü tehlikeli
THRESHOLD_GAS_PPM  = 400.0  # ppm üstü tehlikeli
THRESHOLD_NOISE_DB = 85.0   # dB üstü tehlikeli

# Raspberry Pi BCM pin numaraları
DHT22_PIN    = 4    # fiziksel pin 7
MQ135_DO_PIN = 17   # fiziksel pin 11
KY038_DO_PIN = 27   # fiziksel pin 13

# MCP3008 ADC kanal numaraları (0-7)
MQ135_AO_CHANNEL = 0   # MCP3008 CH0 — MQ135 AO pini
KY038_AO_CHANNEL = 1   # MCP3008 CH1 — KY038 AO pini

SENSOR_PUBLISH_INTERVAL = 2.0  # saniye

import os as _os
LOG_FILE_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "logs", "ohs_robot.log")
