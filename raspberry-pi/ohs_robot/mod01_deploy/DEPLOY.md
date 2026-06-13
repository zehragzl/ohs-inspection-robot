# MOD-01 — Raspberry Pi 5 Deploy Rehberi

## Gereksinimler

- Raspberry Pi 5 (4 GB+ RAM önerilir)
- Pi OS Bookworm (64-bit)
- Raspberry Pi Kamera Modülü (CSI/LibCamera uyumlu)
- Python 3.11 (Bookworm'da varsayılan)

---

## 1. Sistem Paketleri

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-picamera2 mosquitto mosquitto-clients python3-venv
sudo systemctl enable --now mosquitto
```

---

## 2. Kamerayı Etkinleştir

```bash
sudo raspi-config
# → Interface Options → Camera → Enable
sudo reboot
```

Doğrulama (reboot sonrası):
```bash
libcamera-hello --timeout 3000
```

---

## 3. Dosyaları Kopyala

Geliştirici makinesinden:
```bash
rsync -av --exclude='venv/' --exclude='*.zip' --exclude='__pycache__/' \
  ~/Desktop/ceng/ pi@raspberrypi.local:/home/pi/ceng/
```

Kopyalanacak kritik dosyalar:
- `best.onnx` (~12 MB)
- `inference.py`
- `service.py`
- `evaluate.py`
- `mod01-ppe.service`
- `requirements.txt`

---

## 4. Python Sanal Ortam

```bash
cd /home/pi/ceng
python3 -m venv venv --system-site-packages   # system-site-packages: picamera2 erişimi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Not:** `--system-site-packages` ile `apt`'ten kurulan `picamera2` venv içinde görünür.

---

## 5. Smoke Test (PiCamera2 ile)

```bash
cd /home/pi/ceng && source venv/bin/activate
python service.py --once
```

Beklenen çıktı:
```
[service] MOD-01 PPE Servisi başlatıldı.
[smoke_wp_0001]  XXX.Xms  temiz | tespitler: N
==================================================
Çalıştırma özeti (1 inference)
  Ortalama latency : XXX.X ms
  Hedef <500ms    : ✅ PASS     ← Pi 5 CPU hedefi
==================================================
```

---

## 6. Latency & CPU Doğrulama

```bash
# 10 frame ile latency istatistiği
python service.py --image ppe_dataset/test/images/<bir_gorsel>.jpg --once
# veya kamera ile
python service.py --once

# CPU kullanımı (ayrı terminal)
htop
```

**Hedefler:**
| Metrik | Hedef |
|---|---|
| Inference latency | < 500 ms |
| CPU (tek çekirdek) | ≤ 70% |

> Latency > 500ms ise: `PPE_ONNX_THREADS=4` dene veya 640px export'a geç (`best_640.onnx`).

---

## 7. MQTT Smoke Test

İki terminal:
```bash
# Terminal 1 — dinle
mosquitto_sub -t ohs/ppe/violation -v

# Terminal 2 — tetikle (kamera olmadan)
python service.py --image ppe_dataset/test/images/<ihlal_iceren>.jpg --once
```

Beklenen payload:
```json
{
  "class": "NO-Hardhat",
  "confidence": 0.617,
  "bounding_box": [1233, 247, 1450, 478],
  "timestamp": "2026-06-02T10:00:00Z"
}
```

---

## 8. systemd Servisi

```bash
sudo cp /home/pi/ceng/mod01-ppe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mod01-ppe
sudo systemctl status mod01-ppe
```

Log izleme:
```bash
journalctl -u mod01-ppe -f
```

Reboot testi:
```bash
sudo reboot
# 30 saniye sonra
journalctl -u mod01-ppe --since "5 minutes ago"
```

---

## 9. MOD-03 Entegrasyonu (same-process)

MOD-03 Python kodunda:
```python
from inference import init, nav_waypoint_cb

# Robot başlangıcında bir kere çağır
init()

# DWELLING state'ine girildiğinde
def on_waypoint_reached(waypoint_id: str):
    result = nav_waypoint_cb(waypoint_id=waypoint_id)
    if result["violations"]:
        # Kendi MQTT publish'in veya UI güncellemen
        handle_violations(result["violations"])
    return result
```

---

## 10. Ortam Değişkenleri (İnce Ayar)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `PPE_MODEL_PATH` | `<script_dizini>/best.onnx` | ONNX model dosyası |
| `PPE_MQTT_BROKER` | `localhost` | Broker IP/hostname |
| `PPE_MQTT_PORT` | `1883` | Broker portu |
| `PPE_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PPE_ONNX_THREADS` | `2` | Inference thread sayısı |

---

---

## 11. Mac Üzerinde Geçici Test (Pi'siz)

> Pi'ye erişim olmadığında Mac + Mac dahili kamera ile MOD-01'i tam olarak test etmek için.
> Robotik taraf (MOD-03) Windows'ta çalışır; MQTT broker Mac'te kurulur.

### 11.1 Mosquitto Broker (Mac)

```bash
brew install mosquitto
```

Varsayılan mosquitto yalnızca localhost dinler. LAN'a (Windows'a) açmak için:

```bash
# Dosyayı düzenle
nano /opt/homebrew/etc/mosquitto/mosquitto.conf
```

Şu iki satırı ekle (dosyanın sonuna):
```
listener 1883 0.0.0.0
allow_anonymous true
```

Servisi başlat / yeniden başlat:
```bash
brew services start mosquitto
# veya zaten çalışıyorsa:
brew services restart mosquitto
```

Doğrulama:
```bash
mosquitto_sub -t ohs/ppe/violation -v &
mosquitto_pub -t ohs/ppe/violation -m '{"test":1}'
```

### 11.2 Mac LAN IP'si

```bash
ipconfig getifaddr en0      # Wi-Fi
# veya
ipconfig getifaddr en1      # Ethernet
```

Çıkan IP'yi Windows robotik tarafına ver (`PPE_MQTT_BROKER=<bu-ip>`).

### 11.3 Windows tarafında MQTT test

```powershell
# Mosquitto Windows binary veya WSL:
mosquitto_sub -h <mac-ip> -p 1883 -t ohs/ppe/violation -v
```

Mac'te kamerayı tut; ihlal tespiti gelince Windows terminalinde payload görünmeli:
```json
{"class": "NO-Hardhat", "confidence": 0.62, "bounding_box": [...], "timestamp": "..."}
```

### 11.4 Mac Güvenlik Duvarı

System Settings → Network → Firewall → Options → Incoming connections için
`mosquitto` uygulamasına **izin ver** (veya güvenlik duvarını geçici kapat).

### 11.5 Mac Kamera + Önizleme ile Çalıştırma

```bash
cd ~/Desktop/ceng
source venv/bin/activate

# Canlı kamera penceresi + MQTT publish (broker Mac'te)
PPE_MQTT_BROKER=localhost python service.py --preview --interval 0

# Sadece log, pencere yok
PPE_MQTT_BROKER=localhost python service.py --interval 0

# Kamera dizini değiştirmek için (varsayılan 0 = dahili kamera)
PPE_CAMERA_INDEX=1 python service.py --preview --interval 0
```

**Önizleme penceresi tuşları:**
| Tuş | Eylem |
|-----|-------|
| `q` veya `ESC` | Çıkış |

Tespitler: yeşil kutu = güvenli ekipman / kişi, **kırmızı kutu = ihlal**.

### 11.6 Ortam Değişkenleri (Mac-özel)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `PPE_CAMERA_INDEX` | `0` | OpenCV kamera dizini (0 = dahili kamera) |
| `PPE_MQTT_BROKER` | `localhost` | Mac broker için `localhost` yeterli |

---

## Bilinen Sınırlılıklar

| Risk | Açıklama |
|---|---|
| R-01-05 | NO-Safety Vest mAP 0.706 (hedef 0.82) — bilinen limitasyon |
| Model boyutu | 12 MB (spec <10 MB — kabul edildi) |
| Box kalitesi | Model GT'den tighter kutular üretiyor; alarm konumu doğru |
| R-01-03 | Tek frame — v0.2'de burst mod planlanıyor |
