// Raspberry Pi bağlantı ayarları
export const MQTT_CONFIG = {
  PI_IP: '10.196.157.191',      // ← Pi'nin IP'sini buraya yaz (hostname -I)
  PI_MQTT_WS_PORT: 9001,       // Mosquitto WebSocket portu
  RECONNECT_PERIOD: 3000,
  CONNECT_TIMEOUT: 10000,
}

export const TOPICS = {
  PPE_VIOLATION: 'ohs/ppe/violation',
  ENV_HAZARD: 'ohs/env/hazard',
  NAV_POSITION: 'ohs/nav/position',
  NAV_WAYPOINT: 'ohs/nav/waypoint',
  ROBOT_FEEDBACK: 'ohs/robot/feedback',
  ROBOT_COMMAND: 'ohs/robot/command',
  CAMERA_FRAME: 'ohs/camera/frame',
}
