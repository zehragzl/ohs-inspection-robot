import json
import threading
import socket
import time
import paho.mqtt.client as mqtt
from utils.logger import get_logger

_RC_MESSAGES = {
    0: "Connection accepted",
    1: "Connection refused — incorrect protocol version",
    2: "Connection refused — invalid client identifier",
    3: "Connection refused — server unavailable",
    4: "Connection refused — bad username or password",
    5: "Connection refused — not authorised",
}


class MQTTClientBase:
    def __init__(self, client_id: str, broker_host: str, broker_port: int, username: str = "", password: str = ""):
        self._client_id = client_id
        self._broker_hosts = [host.strip() for host in broker_host.split(",") if host.strip()]
        self._broker_port = broker_port
        self._username = username
        self._password = password
        self._logger = get_logger(f"mqtt.{client_id}")
        self._lock = threading.Lock()
        self._connected = False

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if self._username:
            self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def connect(self):
        max_retries = 3
        last_error = None

        for broker_host in self._broker_hosts:
            for attempt in range(1, max_retries + 1):
                try:
                    self._logger.info(
                        "Connecting to broker %s:%d (attempt %d/%d)",
                        broker_host, self._broker_port, attempt, max_retries,
                    )
                    self._client.connect(broker_host, self._broker_port, keepalive=60)
                    self._logger.info("Broker selected: %s:%d", broker_host, self._broker_port)
                    return
                except Exception as exc:
                    last_error = exc
                    self._logger.error("Connection attempt %d to %s failed: %s", attempt, broker_host, exc)
                    if isinstance(exc, socket.gaierror):
                        break
                    if attempt < max_retries:
                        time.sleep(5)

        raise ConnectionError(
            f"Could not connect to broker(s) {', '.join(self._broker_hosts)}:{self._broker_port} "
            f"after {max_retries} attempts each: {last_error}"
        )

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
        self._logger.info("Disconnected from broker")

    def loop_start(self):
        self._client.loop_start()

    def loop_stop(self):
        self._client.loop_stop()

    def publish(self, topic: str, payload_dict: dict, qos: int = 0):
        try:
            payload_str = json.dumps(payload_dict)
            result = self._client.publish(topic, payload_str, qos=qos)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._logger.debug("Published to %s: %s", topic, payload_str)
            else:
                self._logger.error(
                    "Publish to %s failed with rc=%d", topic, result.rc
                )
        except Exception as exc:
            self._logger.error("Publish error on topic %s: %s", topic, exc)

    def subscribe(self, topic: str, callback, qos: int = 0):
        def _message_handler(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                callback(payload)
            except json.JSONDecodeError as exc:
                self._logger.error(
                    "JSON parse error on topic %s: %s | raw: %s",
                    msg.topic, exc, msg.payload,
                )

        self._client.subscribe(topic, qos=qos)
        self._client.message_callback_add(topic, _message_handler)
        self._logger.info("Subscribed to %s (qos=%d)", topic, qos)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        rc = reason_code.value if hasattr(reason_code, "value") else int(reason_code)
        msg = _RC_MESSAGES.get(rc, f"Unknown rc={rc}")
        with self._lock:
            self._connected = (rc == 0)
        if rc == 0:
            self._logger.info("Connected to broker: %s", msg)
        else:
            self._logger.error("Connection failed: %s", msg)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        rc = reason_code.value if hasattr(reason_code, "value") else int(reason_code)
        with self._lock:
            self._connected = False
        if rc == 0:
            self._logger.info("Clean disconnect from broker")
        else:
            self._logger.warning(
                "Unexpected disconnect (rc=%d), auto-reconnect active", rc
            )
