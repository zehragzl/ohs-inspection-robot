"""
MOD-02 Çevresel Sensör Modülü - Gerçek Donanım Entegrasyonu
Sensörler: DHT22 (sıcaklık/nem), MQ135 (gaz/hava kalitesi), KY038 (ses)
"""

import threading
from datetime import datetime, timezone

from config.settings import (
    TOPIC_ENV_HAZARD,
    THRESHOLD_TEMP_C,
    THRESHOLD_HUMIDITY,
    THRESHOLD_GAS_PPM,
    THRESHOLD_NOISE_DB,
    DHT22_PIN,
    MQ135_DO_PIN,
    KY038_DO_PIN,
    MQ135_AO_CHANNEL,
    KY038_AO_CHANNEL,
    SENSOR_PUBLISH_INTERVAL,
)
from mqtt.client_base import MQTTClientBase
from utils.logger import get_logger

# Pi 5 uyumlu GPIO: gpiozero (lgpio backend)
_GPIO_LIB   = None
_gpio_mq135 = None
_gpio_ky038 = None

try:
    from gpiozero import DigitalInputDevice as _DigInput
    _gpio_mq135 = _DigInput(MQ135_DO_PIN, pull_up=None, active_state=False)
    _gpio_ky038 = _DigInput(KY038_DO_PIN, pull_up=None, active_state=False)
    _GPIO_LIB = "gpiozero"
except Exception:
    pass

# MCP3008 ADC — spidev ile analog okuma (GPIO çakışması yok)
_MCP_LIB = None
_spi_dev = None

try:
    import spidev as _spidev_mod
    _spi_dev = _spidev_mod.SpiDev()
    _spi_dev.open(0, 0)
    _spi_dev.max_speed_hz = 1350000
    _MCP_LIB = "spidev"
except Exception:
    pass

def _read_mcp3008_voltage(channel: int) -> float | None:
    if _spi_dev is None:
        return None
    try:
        r = _spi_dev.xfer2([1, (8 + channel) << 4, 0])
        return (((r[1] & 3) << 8) + r[2]) * 3.3 / 1023.0
    except Exception:
        return None

# DHT22 kütüphane tespiti: önce yeni (adafruit_dht), sonra eski (Adafruit_DHT)
_DHT_LIB = None
_DHT_DEVICE = None
_Adafruit_DHT = None

try:
    import adafruit_dht as _adafruit_dht_mod
    import board as _board_mod
    _dht_pin = getattr(_board_mod, f"D{DHT22_PIN}", None)
    if _dht_pin is None:
        raise ImportError(f"board.D{DHT22_PIN} bulunamadı")
    _DHT_DEVICE = _adafruit_dht_mod.DHT22(_dht_pin)
    _DHT_LIB = "adafruit_dht"
except Exception:
    try:
        import Adafruit_DHT as _Adafruit_DHT
        _DHT_LIB = "Adafruit_DHT"
    except ImportError:
        pass  # _DHT_LIB = None → simülasyon


class EnvSensorModule:
    """
    Gerçek DHT22, MQ135 ve KY038 sensörlerinden veri okuyup
    ohs/env/hazard topic'ine publish eden modül.
    """

    def __init__(self, mqtt_client: MQTTClientBase):
        self._client = mqtt_client
        self._logger = get_logger("mod02.env")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._setup_gpio()

    # ------------------------------------------------------------------
    # GPIO Kurulum
    # ------------------------------------------------------------------

    def _setup_gpio(self):
        self._logger.info("[MOD-02] DHT22 kütüphanesi: %s", _DHT_LIB or "YOK (simülasyon)")
        self._logger.info("[MOD-02] MCP3008 ADC: %s", _MCP_LIB or "YOK (DO pin kullanılıyor)")
        if _GPIO_LIB:
            self._logger.info(
                "[MOD-02] GPIO kütüphanesi: %s — MQ135=%s, KY038=%s",
                _GPIO_LIB, MQ135_DO_PIN, KY038_DO_PIN,
            )
        else:
            self._logger.info("[MOD-02] GPIO kütüphanesi YOK — simülasyon modunda çalışılıyor.")

    # ------------------------------------------------------------------
    # Thread Yönetimi
    # ------------------------------------------------------------------

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="mod02-env", daemon=True
        )
        self._thread.start()
        self._logger.info("[MOD-02] EnvSensorModule started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        self._cleanup_gpio()
        self._logger.info("[MOD-02] EnvSensorModule stopped")

    def _cleanup_gpio(self):
        if _DHT_LIB == "adafruit_dht" and _DHT_DEVICE is not None:
            try:
                _DHT_DEVICE.exit()
            except Exception:
                pass
        for dev in (_gpio_mq135, _gpio_ky038):
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
        if _spi_dev is not None:
            try:
                _spi_dev.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Ana Döngü
    # ------------------------------------------------------------------

    def _loop(self):
        while not self._stop_event.wait(SENSOR_PUBLISH_INTERVAL):
            self._read_and_publish_all()

    def _read_and_publish_all(self):
        temp, humidity = self._read_dht22()
        if temp is not None:
            self._publish_sensor_value(
                sensor="dht22", metric="temperature",
                value=temp, threshold=THRESHOLD_TEMP_C, unit="°C",
            )
        if humidity is not None:
            self._publish_sensor_value(
                sensor="dht22", metric="humidity",
                value=humidity, threshold=THRESHOLD_HUMIDITY, unit="%",
            )

        gas_ppm = self._read_gas_ppm()
        if gas_ppm is not None:
            self._publish_sensor_value(
                sensor="mq135", metric="gas_ppm",
                value=gas_ppm, threshold=THRESHOLD_GAS_PPM, unit="ppm",
            )

        noise_db = self._read_noise_db()
        if noise_db is not None:
            self._publish_sensor_value(
                sensor="ky038", metric="noise_db",
                value=noise_db, threshold=THRESHOLD_NOISE_DB, unit="dB",
            )

    # ------------------------------------------------------------------
    # Sensör Okuma Fonksiyonları
    # ------------------------------------------------------------------

    def _read_dht22(self) -> tuple[float | None, float | None]:
        """DHT22'den (temperature_C, humidity_pct) döner; donanım yoksa simüle eder."""
        if _DHT_LIB == "adafruit_dht":
            try:
                temp = _DHT_DEVICE.temperature
                hum  = _DHT_DEVICE.humidity
                if temp is None:
                    self._logger.warning("[MOD-02] DHT22 sıcaklık verisi boş döndü.")
                if hum is None:
                    self._logger.warning("[MOD-02] DHT22 nem verisi boş döndü.")
                return (round(float(temp), 2) if temp is not None else None,
                        round(float(hum),  2) if hum  is not None else None)
            except RuntimeError as exc:
                # DHT22 arada sırada okuma hatası verir; bir sonraki döngüde tekrar dener
                self._logger.warning("[MOD-02] DHT22 geçici okuma hatası: %s", exc)
                return None, None
            except Exception as exc:
                self._logger.error("[MOD-02] DHT22 okuma hatası: %s", exc)
                return None, None

        if _DHT_LIB == "Adafruit_DHT":
            try:
                humidity, temperature = _Adafruit_DHT.read_retry(
                    _Adafruit_DHT.DHT22, DHT22_PIN
                )
                temp = round(float(temperature), 2) if temperature is not None else None
                hum  = round(float(humidity),    2) if humidity    is not None else None
                if temp is None:
                    self._logger.warning("[MOD-02] DHT22 sıcaklık verisi boş döndü.")
                if hum is None:
                    self._logger.warning("[MOD-02] DHT22 nem verisi boş döndü.")
                return temp, hum
            except Exception as exc:
                self._logger.error("[MOD-02] DHT22 okuma hatası: %s", exc)
                return None, None

        # Simülasyon
        import random
        return round(random.uniform(20.0, 35.0), 2), round(random.uniform(40.0, 70.0), 2)

    def _read_gas_ppm(self) -> float | None:
        """MQ135 → PPM. MCP3008 varsa AO pinden analog, yoksa DO pinden binary okur."""
        if _MCP_LIB:
            v = _read_mcp3008_voltage(MQ135_AO_CHANNEL)
            if v is not None:
                try:
                    return self._voltage_to_gas_ppm(v)
                except Exception as exc:
                    self._logger.error("[MOD-02] MQ135 analog okuma hatası: %s", exc)
                    return None
        if _GPIO_LIB and _gpio_mq135 is not None:
            try:
                hazard = _gpio_mq135.is_active
                return THRESHOLD_GAS_PPM + 50 if hazard else THRESHOLD_GAS_PPM - 50
            except Exception as exc:
                self._logger.error("[MOD-02] MQ135 okuma hatası: %s", exc)
                return None
        import random
        return THRESHOLD_GAS_PPM + 50 if random.random() < 0.1 else THRESHOLD_GAS_PPM - 50

    def _read_noise_db(self) -> float | None:
        """KY038 → dB. MCP3008 varsa AO pinden analog, yoksa DO pinden binary okur."""
        if _MCP_LIB:
            v = _read_mcp3008_voltage(KY038_AO_CHANNEL)
            if v is not None:
                try:
                    return self._voltage_to_noise_db(v)
                except Exception as exc:
                    self._logger.error("[MOD-02] KY038 analog okuma hatası: %s", exc)
                    return None
        if _GPIO_LIB and _gpio_ky038 is not None:
            try:
                hazard = _gpio_ky038.is_active
                return THRESHOLD_NOISE_DB + 10 if hazard else THRESHOLD_NOISE_DB - 10
            except Exception as exc:
                self._logger.error("[MOD-02] KY038 okuma hatası: %s", exc)
                return None
        import random
        return THRESHOLD_NOISE_DB + 10 if random.random() < 0.15 else THRESHOLD_NOISE_DB - 10

    @staticmethod
    def _voltage_to_gas_ppm(voltage: float) -> float:
        """MQ135 AO voltajı → tahmini PPM (kalibrasyon olmadan yaklaşık değer)."""
        if voltage <= 0.01:
            return 1000.0
        ratio = (3.3 - voltage) / voltage  # Rs/RL oranı
        ppm = 110.0 * (ratio ** -2.77)     # MQ135 CO2 eğrisi yaklaşımı
        return round(max(100.0, min(2000.0, ppm)), 1)

    @staticmethod
    def _voltage_to_noise_db(voltage: float) -> float:
        """KY038 AO voltajı → tahmini dB (0V=30dB, 3.3V=100dB)."""
        db = 30.0 + (voltage / 3.3) * 70.0
        return round(max(30.0, min(120.0, db)), 1)

    # ------------------------------------------------------------------
    # MQTT Publish
    # ------------------------------------------------------------------

    def _publish_sensor_value(self, sensor: str, metric: str,
                               value: float, threshold: float, unit: str):
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload = {
            "timestamp": ts,
            "sensor": sensor,
            "metric": metric,
            "value": round(value, 2),
            "threshold": threshold,
            "unit": unit,
            "hazard": value >= threshold,
        }

        if payload["hazard"]:
            self._logger.warning(
                "[MOD-02][HAZARD] sensor=%s metric=%s value=%s %s (eşik: %s)",
                sensor, metric, value, unit, threshold,
            )
        else:
            self._logger.debug(
                "[MOD-02] sensor=%s metric=%s value=%s %s", sensor, metric, value, unit
            )

        self._client.publish(TOPIC_ENV_HAZARD, payload, qos=0)
