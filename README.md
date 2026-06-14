# Vision and Sensor-Based Autonomous OHS Inspection Robot

> **Gebze Technical University — CSE 396 Computer Engineering Project · Spring 2026**  
> Group 8 · Instructor: Salih Sarp

An autonomous mobile robot that patrols industrial workplaces, detects PPE violations using a deep-learning camera module, monitors environmental hazards with onboard sensors, and streams real-time safety alerts to an operator dashboard — all without requiring a human inspector to be present in the hazard area.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Hardware](#hardware)
- [Modules](#modules)
- [Quick Start](#quick-start)
- [MQTT Topics](#mqtt-topics)
- [Running the System](#running-the-system)
- [Testing](#testing)
- [Team](#team)

---

## Overview

The system integrates five software modules across three hardware tiers:

| Module | Description | Runs on |
|--------|-------------|---------|
| **MOD-01** | Vision-Based PPE Detection (YOLOv8n + ONNX Runtime) | Raspberry Pi 5 |
| **MOD-02** | Environmental Hazard Sensing (DHT22 / MQ-135 / KY-038) | Raspberry Pi 5 |
| **MOD-03** | Autonomous Navigation (waypoint patrol + Arduino motor control) | Raspberry Pi 5 |
| **MOD-04** | Backend & REST API (Spring Boot 3 + PostgreSQL 16) | Remote Server |
| **MOD-05** | OHS Monitoring Dashboard (React.js + Electron) | Operator PC |

All edge modules communicate through an **Eclipse Mosquitto MQTT broker** running on the Raspberry Pi 5. The backend subscribes to all topics, persists events, and pushes live alerts to the dashboard via WebSocket/STOMP.

---

## System Architecture

```
┌─────────────────────────────────────────────────┐
│               Raspberry Pi 5                    │
│                                                 │
│  MOD-01        MOD-02        MOD-03             │
│  PPE Det.   Env. Sensing   Navigation           │
│      │            │             │               │
│      └────────────┴─────────────┘               │
│                   │                             │
│         Eclipse Mosquitto :1883                 │
└───────────────────┬─────────────────────────────┘
                    │ USB Serial (115200 baud)
              ┌─────┴──────┐
              │ Arduino UNO│  ← L298N → 4× DC Motors
              │    R3      │  ← HC-SR04 × 2 (obstacle)
              └────────────┘

                    │ MQTT (LAN)
┌───────────────────┴─────────────────────────────┐
│              Remote Server                      │
│   MOD-04: Spring Boot 3 + PostgreSQL 16         │
│   REST :8080  │  WebSocket/STOMP :8080/ws       │
└───────────────────┬─────────────────────────────┘
                    │ WebSocket + REST
┌───────────────────┴─────────────────────────────┐
│              Operator PC                        │
│   MOD-05: React.js + Electron Dashboard         │
└─────────────────────────────────────────────────┘
```

**Latency targets:**
- Violation → dashboard: **< 2 s**
- Operator command acknowledgement: **< 5 s**
- Obstacle detection → motor stop: **< 100 ms**

---

## Hardware

| Component | Role |
|-----------|------|
| Raspberry Pi 5 (8 GB) | Main edge computer |
| Arduino UNO R3 | Real-time motor controller |
| L298N Dual H-Bridge | Motor driver (4× DC motors) |
| Raspberry Pi Camera Module v2 | PPE detection camera (MIPI CSI) |
| DHT22 | Temperature (°C) and humidity (%) |
| MQ-135 | Gas / air-quality sensor (CO₂ / VOC in PPM) |
| KY-038 | Ambient noise sensor (dB) |
| HC-SR04 × 2 | Ultrasonic obstacle detection (halt < 20 cm) |
| MCP3008 (SPI ADC) | Analog reading for MQ-135 and KY-038 |
| Battery Pack × 5 | 3 batteries → Pi/Arduino (USB), 2 batteries → motors (separate rails) |

> **Power note:** The motors and the Raspberry Pi must be on **separate power rails**. Running them from the same source causes Arduino resets under motor load.

---

## Modules

### MOD-01 — Vision-Based PPE Detection
- Runs YOLOv8n inference via **ONNX Runtime** on the Pi 5 CPU
- Captures frames from Raspberry Pi Camera Module v2 via **PiCamera2**
- Detects: `no_helmet`, `no_vest`, `no_goggles`
- Publishes violations to `ohs/ppe/violation`
- Falls back to simulation mode if camera or model is unavailable

### MOD-02 — Environmental Hazard Sensing
- Reads **DHT22** (temperature, humidity), **MQ-135** (gas PPM via MCP3008 SPI ADC), **KY-038** (noise dB)
- Uses **gpiozero** with the **lgpio backend** (required for Raspberry Pi 5 GPIO compatibility)
- Publishes threshold breaches to `ohs/env/hazard`
- Falls back to simulation mode if sensors are unavailable

### MOD-03 — Autonomous Navigation
- Follows a predefined waypoint list using **time-based dead-reckoning**
- Sends timed ASCII commands (`FORWARD / BACK / LEFT / RIGHT + ms`) to the Arduino over USB serial (115200 baud)
- Halts the robot when HC-SR04 detects an obstacle within 20 cm
- Subscribes to `ohs/robot/command` for START / STOP / ALARM from the dashboard
- Publishes position to `ohs/nav/position`

### MOD-04 — Backend & REST API
- **Spring Boot 3**, Java 17, PostgreSQL 16, Flyway migrations
- Subscribes to all MQTT topics; persists every event to the database
- REST API: `GET /api/v1/events` (filtered, paginated history)
- WebSocket/STOMP: pushes new events to the dashboard in real time
- Forwards operator commands (`START / STOP / ALARM`) back to MQTT

### MOD-05 — OHS Monitoring Dashboard
- **React.js** SPA packaged as an **Electron** desktop app
- **Leaflet.js** floor-plan overlay with colour-coded violation markers
- Live sensor gauge panels (temperature, humidity, gas, noise)
- Operator command buttons (START / STOP / ALARM)
- Connects to MOD-04 via WebSocket (live events) and REST (history on load)

---

## Quick Start

### Prerequisites

**Raspberry Pi 5 (edge):**
```bash
# Python 3.11+
sudo apt update && sudo apt install -y mosquitto mosquitto-clients python3-pip

pip install -r requirements.txt --break-system-packages
```

**Remote Server (backend):**
- Java 17+
- PostgreSQL 16
- Maven 3.9+

**Operator PC (dashboard):**
- Node.js 20+
- npm

---

### Edge Setup (Raspberry Pi 5)

```bash
# 1. Clone the repository
git clone https://github.com/zehragzl/ohs-inspection-robot.git
cd ohs-inspection-robot

# 2. Install Python dependencies
pip install -r requirements.txt --break-system-packages

# 3. Start the Mosquitto broker
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# 4. Run the edge system
python main.py
```

The system starts in **simulation mode** automatically if the camera, sensors, or Arduino are not detected. No hardware required for software testing.

---

### Backend Setup (Remote Server)

```bash
cd backend   # MOD-04 Spring Boot project

# Configure database and MQTT in:
# src/main/resources/application.properties

mvn clean package -DskipTests
java -jar target/ohs-backend.jar
```

---

### Dashboard Setup (Operator PC)

```bash
cd dashboard   # MOD-05 React + Electron project
npm install
npm start        # browser mode
npm run electron # desktop app mode
```

---

## MQTT Topics

| Topic | Direction | Publisher | Description |
|-------|-----------|-----------|-------------|
| `ohs/ppe/violation` | Publish | MOD-01 | PPE violation detected (class, confidence, bounding box, timestamp) |
| `ohs/env/hazard` | Publish | MOD-02 | Environmental hazard breach (metric, value, unit, threshold, timestamp) |
| `ohs/nav/position` | Publish | MOD-03 | Robot position at waypoint arrival (x_m, y_m, waypoint_id, state) |
| `ohs/nav/waypoint` | Publish | MOD-03 | Waypoint arrival notification |
| `ohs/robot/feedback` | Publish | MOD-03 | Command acknowledgement (correlationId, status, detail) |
| `ohs/robot/command` | Subscribe | MOD-03 | Operator commands from dashboard (START / STOP / ALARM) |

### Example Payloads

**PPE violation (`ohs/ppe/violation`):**
```json
{
  "class": "no_helmet",
  "confidence": 0.87,
  "bbox": [120, 45, 310, 280],
  "timestamp": "2026-05-18T14:32:10Z",
  "source": "picamera2"
}
```

**Environmental hazard (`ohs/env/hazard`):**
```json
{
  "hazard": true,
  "metric": "gas_ppm",
  "value": 512.3,
  "unit": "ppm",
  "threshold": 400,
  "timestamp": "2026-05-18T14:32:15Z"
}
```

**Navigation position (`ohs/nav/position`):**
```json
{
  "waypoint_id": 3,
  "x_m": 2.00,
  "y_m": 3.00,
  "state": "DWELLING",
  "obstacle_cm": 182,
  "timestamp_ms": 34287
}
```

---

## Running the System

Run the components in this order. Each step requires its own terminal.

---

### Step 1 — Start the MQTT Broker (Raspberry Pi 5)

```bash
sudo systemctl start mosquitto
```

Verify it is running:
```bash
sudo systemctl status mosquitto
# Should show: Active: active (running)
```

---

### Step 2 — Start the Edge System (Raspberry Pi 5)

```bash
cd ohs-inspection-robot
python main.py
```

Expected output:
```
INFO  main   — OHS Robot starting up
INFO  main   — Robot connected: /dev/ttyUSB0        ← real hardware
# or
WARN  main   — Robot not found — running in simulation mode
INFO  mod01  — PPE detection started
INFO  mod02  — Env sensor module started
INFO  mod03  — Navigation started
INFO  main   — All modules running. Press Ctrl+C to stop.
```

To stop: `Ctrl+C`

---

### Step 3 — Start the Backend (Remote Server)

```bash
cd backend
java -jar target/ohs-backend.jar
```

Expected output:
```
Started OhsBackendApplication in 3.2 seconds
MQTT connected to broker
REST API listening on :8080
WebSocket/STOMP listening on :8080/ws
```

---

### Step 4 — Open the Dashboard (Operator PC)

```bash
cd dashboard
npm start          # browser at http://localhost:3000
npm run electron   # desktop app
```

Once connected you will see the floor plan, live sensor gauges, and START / STOP / ALARM buttons.

---

### Sending a Command from Terminal

```bash
mosquitto_pub -h <PI_IP> -t ohs/robot/command \
  -m '{"cmd":"START","correlationId":"manual-001","issuedBy":"operator","timestamp":"2026-01-01T00:00:00Z"}'
```

---

## Testing

### Listen to all MQTT topics
```bash
mosquitto_sub -h localhost -t "ohs/#" -v
```

### Send test commands
```bash
# STOP
mosquitto_pub -h localhost -t ohs/robot/command \
  -m '{"cmd":"STOP","correlationId":"test-001","issuedBy":"test","timestamp":"2026-05-18T20:14:00Z"}'

# START
mosquitto_pub -h localhost -t ohs/robot/command \
  -m '{"cmd":"START","correlationId":"test-002","issuedBy":"test","timestamp":"2026-05-18T20:14:10Z"}'

# ALARM
mosquitto_pub -h localhost -t ohs/robot/command \
  -m '{"cmd":"ALARM","correlationId":"test-003","issuedBy":"test","timestamp":"2026-05-18T20:14:20Z"}'
```

Expected: each command triggers a feedback message on `ohs/robot/feedback` with matching `correlationId` and `status: OK`.

---

## Team

| Name | Role | Module |
|------|------|--------|
| **Zehra Betül Güzel** ⭐ | Team Captain | MOD-02 — Environmental Hazard Sensing |
| Melik Ahmet Caymazoğlu | | MOD-01 — Vision-Based PPE Detection |
| Mert Certel | | MOD-01 — Vision-Based PPE Detection |
| Ahmet Faruk Kemal Keskinsoy | | MOD-03 — Autonomous Navigation |
| Muhammed Emin Merdun | | MOD-03 — Autonomous Navigation |
| Ömer Faruk Semih | | MOD-04 — Backend & REST API |
| Yusuf Eren Nalbant | | MOD-04 — Backend & REST API |
| İrem Akşun | | MOD-05 — OHS Monitoring Dashboard |

---

> Gebze Technical University · Department of Computer Engineering · Spring 2026
