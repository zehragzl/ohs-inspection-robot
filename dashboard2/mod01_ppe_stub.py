"""
MOD-01 PPE Detection — gerçek kamera + ONNX modeli varsa kullanır,
yoksa stub (simüle) modunda çalışır.
"""

import os
import random
import threading
from datetime import datetime, timezone

from config.settings import TOPIC_PPE_VIOLATION, PPE_PUBLISH_INTERVAL
from mqtt.client_base import MQTTClientBase
from utils.logger import get_logger

_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mod01_deploy", "best.onnx")

_HAS_MODEL = os.path.exists(_MODEL_PATH)

if _HAS_MODEL:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "mod01_deploy"))
    try:
        from inference import init as _inf_init, capture_frame, ppe_run_inference, release_camera, start_stream_server
        _HAS_INFERENCE = True
    except ImportError as _e:
        _HAS_INFERENCE = False
        _import_err = str(_e)
else:
    _HAS_INFERENCE = False


class PPEDetectionStub:
    def __init__(self, mqtt_client: MQTTClientBase):
        self._client = mqtt_client
        self._logger = get_logger("mod01.ppe")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        if _HAS_MODEL and _HAS_INFERENCE:
            _inf_init(model_path=_MODEL_PATH, connect_mqtt=False)
            start_stream_server(port=8080)
            self._mode = "camera"
            self._logger.info("[MOD-01] Gerçek kamera modu — model: %s", _MODEL_PATH)
        elif _HAS_MODEL and not _HAS_INFERENCE:
            self._mode = "stub"
            self._logger.warning("[MOD-01] Model var ama inference import edilemedi (%s), stub modu.", _import_err)
        else:
            self._mode = "stub"
            self._logger.info("[MOD-01] Model bulunamadı (%s) — stub modu.", _MODEL_PATH)

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="mod01-ppe", daemon=True
        )
        self._thread.start()
        self._logger.info("[MOD-01] PPEDetectionStub started (%s)", self._mode)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        if self._mode == "camera" and _HAS_INFERENCE:
            release_camera()
        self._logger.info("[MOD-01] PPEDetectionStub stopped")

    def _loop(self):
        while not self._stop_event.wait(PPE_PUBLISH_INTERVAL):
            if self._mode == "camera":
                self._detect_and_publish()
            else:
                self._publish_stub()

    # ── Gerçek kamera tespiti ──────────────────────────────────────────

    def _detect_and_publish(self):
        try:
            frame = capture_frame()
            if frame is None:
                self._logger.warning("[MOD-01] Kamera karesi alınamadı, stub'a geçiliyor.")
                self._publish_stub()
                return

            result = ppe_run_inference(frame=frame)
            if not result["success"]:
                return

            ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            violations = result["violations"]

            if violations:
                for v in violations:
                    payload = {
                        "class":        v["class"],
                        "confidence":   v["confidence"],
                        "bounding_box": v["bounding_box"],
                        "timestamp":    ts,
                        "source":       "camera",
                    }
                    self._logger.warning(
                        "[MOD-01][CAMERA] İhlal: class=%s conf=%.3f latency=%.1fms",
                        v["class"], v["confidence"], result["latency_ms"],
                    )
                    self._client.publish(TOPIC_PPE_VIOLATION, payload, qos=0)
            else:
                self._logger.debug(
                    "[MOD-01][CAMERA] Temiz — %d tespit, %.1fms",
                    len(result["detections"]), result["latency_ms"],
                )
        except Exception as exc:
            self._logger.error("[MOD-01] Kamera inference hatası: %s", exc)

    # ── Stub (simüle) modu ─────────────────────────────────────────────

    def _publish_stub(self):
        payload = {
            "class":        random.choice(["no_helmet", "no_vest", "no_goggles"]),
            "confidence":   round(random.uniform(0.50, 0.99), 4),
            "bounding_box": [
                random.randint(0, 400),
                random.randint(0, 300),
                random.randint(400, 640),
                random.randint(300, 480),
            ],
            "timestamp":    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source":       "stub",
        }
        self._logger.info(
            "[MOD-01][STUB] PPE violation: class=%s confidence=%.4f",
            payload["class"], payload["confidence"],
        )
        self._client.publish(TOPIC_PPE_VIOLATION, payload, qos=0)