import threading
import time
from datetime import datetime, timezone

from config.settings import (
    TOPIC_NAV_POSITION,
    TOPIC_NAV_WAYPOINT,
    TOPIC_NAV_OBSTACLE,
    TOPIC_ROBOT_FEEDBACK,
    TOPIC_ROBOT_COMMAND,
    WAYPOINTS,
    ROBOT_SPEED_MPS,
)
from mqtt.client_base import MQTTClientBase
from utils.logger import get_logger

_STATE_IDLE     = "IDLE"
_STATE_MOVING   = "MOVING"
_STATE_DWELLING = "DWELLING"
_STATE_STOPPED  = "STOPPED"
_STATE_DONE     = "MISSION_COMPLETE"


class NavigationStub:
    """
    Waypoint misyonu: x ekseni boyunca düz ilerleme, sabit derinlik.
    robot parametresi verilirse gerçek seri motor komutları gönderilir;
    verilmezse sadece MQTT yayını yapılır (simülasyon modu).
    """

    def __init__(self, mqtt_client: MQTTClientBase, robot=None):
        self._client = mqtt_client
        self._robot  = robot
        self._logger = get_logger("mod03.nav")
        self._lock        = threading.Lock()
        self._stop_event  = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = _STATE_IDLE

        if robot is not None:
            robot.on_obstacle   = self._on_obstacle
            robot.on_avoid_done = self._on_avoid_done

    # ── yaşam döngüsü ──────────────────────────────────────────────────

    def start(self):
        self._client.subscribe(TOPIC_ROBOT_COMMAND, self._on_command, qos=0)
        self._publish_plan()
        self._stop_event.clear()
        self._set_state(_STATE_MOVING)
        self._thread = threading.Thread(
            target=self._mission_loop, name="mod03-nav", daemon=True
        )
        self._thread.start()
        mode = "ROBOT" if self._robot else "SIM"
        self._logger.info("[MOD-03] NavigationStub başladı (%s modu, %d waypoint)", mode, len(WAYPOINTS))

    def stop(self):
        self._stop_event.set()
        if self._robot:
            self._robot.stop()
        if self._thread:
            self._thread.join(timeout=5)
        self._logger.info("[MOD-03] NavigationStub durduruldu")

    # ── iç yardımcılar ─────────────────────────────────────────────────

    def _publish_plan(self):
        """Başlangıçta tüm waypoint planını dashboard'a gönderir."""
        for wp in WAYPOINTS:
            payload = {
                "timestamp_ms": int(time.time() * 1000),
                "waypoint_id":  wp["id"],
                "label":        wp.get("label", f"WP{wp['id']}"),
                "x_m":          wp["x_m"],
                "y_m":          wp["y_m"],
                "depth_m":      wp["depth_m"],
                "state":        "PLANNED",
            }
            self._client.publish(TOPIC_NAV_WAYPOINT, payload, qos=0)

    def _set_state(self, new_state: str):
        with self._lock:
            self.state = new_state
        self._logger.info("[MOD-03][STATE] -> %s", new_state)

    def _publish_position(self, waypoint: dict, state_label: str):
        payload = {
            "timestamp_ms": int(time.time() * 1000),
            "waypoint_id":  waypoint["id"],
            "label":        waypoint.get("label", f"WP{waypoint['id']}"),
            "x_m":          waypoint["x_m"],
            "y_m":          waypoint["y_m"],
            "depth_m":      waypoint["depth_m"],
            "state":        state_label,
        }
        self._client.publish(TOPIC_NAV_POSITION, payload, qos=0)
        self._client.publish(TOPIC_NAV_WAYPOINT, payload, qos=0)

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Uyurken STOP sinyali gelirse False döner."""
        end = time.time() + seconds
        while time.time() < end:
            if self._stop_event.is_set():
                return False
            with self._lock:
                if self.state == _STATE_STOPPED:
                    return False
            time.sleep(0.1)
        return True

    def _publish_travel_position(self, from_wp: dict, to_wp: dict, travel_sec: float):
        """Hareket sırasında her saniye interpolated konum yayınlar."""
        start = time.time()
        while True:
            if self._stop_event.is_set():
                break
            with self._lock:
                if self.state != _STATE_MOVING:
                    break
            elapsed = time.time() - start
            if elapsed >= travel_sec:
                break
            ratio = min(elapsed / travel_sec, 1.0)
            x_m = from_wp["x_m"] + (to_wp["x_m"] - from_wp["x_m"]) * ratio
            self._client.publish(TOPIC_NAV_POSITION, {
                "timestamp_ms": int(time.time() * 1000),
                "waypoint_id":  to_wp["id"],
                "label":        to_wp.get("label", f"WP{to_wp['id']}"),
                "x_m":          round(x_m, 2),
                "y_m":          to_wp["y_m"],
                "depth_m":      to_wp["depth_m"],
                "state":        _STATE_MOVING,
            }, qos=0)
            time.sleep(1.0)

    def _wait_for_move(self, travel_sec: float) -> bool:
        """
        Arduino gerçek donanımda: STOPPED sinyalini bekler (kaçınma süresi dahil).
        Simülasyonda: interruptible_sleep kullanır.
        False dönerse misyon iptal edilmeli.
        """
        if self._robot:
            self._robot._move_done.clear()
            self._robot.forward(travel_sec)
            # Kaçınma manevrasına (sağ+ileri+sol ≈ 3s) + güvenlik payı
            max_wait = travel_sec + 20.0
            end = time.time() + max_wait
            while time.time() < end:
                if self._stop_event.is_set():
                    self._robot.stop()
                    return False
                with self._lock:
                    if self.state == _STATE_STOPPED:
                        self._robot.stop()
                        return False
                if self._robot._move_done.wait(timeout=0.1):
                    return True
            self._logger.warning("[MOD-03] Hareket zaman aşımı, zorla durduruldu")
            self._robot.stop()
            return True
        else:
            return self._interruptible_sleep(travel_sec)

    def _on_obstacle(self, dist_cm: int):
        """Arduino'dan OBSTACLE sinyali gelince MQTT'ye yayar."""
        self._logger.warning("[MOD-03][OBSTACLE] Engel tespit edildi: %d cm", dist_cm)
        self._client.publish(TOPIC_NAV_OBSTACLE, {
            "timestamp_ms": int(time.time() * 1000),
            "dist_cm":      dist_cm,
            "action":       "avoid_start",
        })

    def _on_avoid_done(self):
        """Arduino kaçınmayı bitirince MQTT'ye yayar."""
        self._logger.info("[MOD-03][OBSTACLE] Kaçınma tamamlandı, yola devam.")
        self._client.publish(TOPIC_NAV_OBSTACLE, {
            "timestamp_ms": int(time.time() * 1000),
            "dist_cm":      0,
            "action":       "avoid_done",
        })

    # ── ana misyon döngüsü ──────────────────────────────────────────────

    def _mission_loop(self):
        total = len(WAYPOINTS)

        for i, wp in enumerate(WAYPOINTS):
            if self._stop_event.is_set():
                break

            is_first = (i == 0)
            is_last  = (i == total - 1)

            # ── hareket ──
            if not is_first:
                prev_wp    = WAYPOINTS[i - 1]
                segment_m  = wp["segment_m"]
                travel_sec = segment_m / ROBOT_SPEED_MPS
                self._set_state(_STATE_MOVING)
                self._logger.info("[MOD-03] WP%d: %.1fm ileri (%.1f sn)", wp["id"], segment_m, travel_sec)

                if not self._wait_for_move(travel_sec):
                    return

            # ── varış ──
            state_label = _STATE_DONE if is_last else _STATE_DWELLING
            self._set_state(state_label)
            self._publish_position(wp, state_label)
            self._logger.info(
                "[MOD-03] WP%d ulaşıldı: x=%.1fm, derinlik=%.2fm — %s",
                wp["id"], wp["x_m"], wp["depth_m"], state_label,
            )

            if is_last:
                self._logger.info("[MOD-03] Misyon tamamlandı.")
                break

            # ── bekleme (dwell) ──
            dwell_sec = wp.get("dwell_ms", 3000) / 1000.0
            self._logger.info("[MOD-03] %.1f sn bekleniyor (kontrol noktası)...", dwell_sec)
            if not self._interruptible_sleep(dwell_sec):
                return

        self._set_state(_STATE_DONE)

    # ── MQTT komut işleyici ─────────────────────────────────────────────

    def _on_command(self, payload: dict):
        cmd = payload.get("cmd", "").upper()
        ts  = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        status, detail = "OK", ""

        if cmd == "START":
            if self.state in (_STATE_DONE, _STATE_IDLE):
                self._stop_event.clear()
                self._set_state(_STATE_MOVING)
                self._thread = threading.Thread(
                    target=self._mission_loop, name="mod03-nav", daemon=True
                )
                self._thread.start()
                detail = "Mission restarted"
            else:
                self._set_state(_STATE_MOVING)
                detail = f"Resumed. New state: {self.state}"

        elif cmd in ("STOP", "ALARM"):
            self._stop_event.set()
            if self._robot:
                self._robot.stop()
            self._set_state(_STATE_STOPPED)
            if cmd == "ALARM":
                self._logger.warning("[MOD-03][ALARM] Robot durduruldu!")
            detail = f"{cmd} executed. State: {self.state}"

        else:
            status = "ERROR"
            detail = f"Unknown command: {cmd!r}"
            self._logger.error("[MOD-03] Bilinmeyen komut: %s", cmd)

        self._client.publish(TOPIC_ROBOT_FEEDBACK, {
            "correlationId": payload.get("correlationId", "unknown"),
            "status":    status,
            "detail":    detail,
            "timestamp": ts,
        })
