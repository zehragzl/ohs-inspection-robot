import signal
import sys
import time

from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_PASSWORD, MQTT_USERNAME, ROBOT_PORT
from mqtt.client_base import MQTTClientBase
from modules.mod01_ppe_stub import PPEDetectionStub
from modules.mod02_env_stub import EnvSensorModule
from modules.mod03_nav_stub import NavigationStub
from utils.logger import get_logger

logger = get_logger("main")

ppe_stub: PPEDetectionStub
env_stub: EnvSensorModule
nav_stub: NavigationStub
client:   MQTTClientBase


def _init_robot():
    """Robot seri bağlantısını dene; başarısız olursa simülasyon modunda devam et."""
    try:
        from robot_control import Robot
        bot = Robot(ROBOT_PORT)
        logger.info("Robot bağlandı: %s", bot.port)
        return bot
    except Exception as exc:
        logger.warning("Robot bağlanamadı (%s) — simülasyon modunda çalışılıyor", exc)
        return None


def graceful_shutdown(sig, frame):
    logger.info("Shutdown signal received (sig=%d)", sig)
    nav_stub.stop()
    env_stub.stop()
    ppe_stub.stop()
    client.loop_stop()
    client.disconnect()
    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    global ppe_stub, env_stub, nav_stub, client

    logger.info("OHS Robot starting up")

    robot = _init_robot()

    client = MQTTClientBase(
        client_id="ohs_robot_main",
        broker_host=MQTT_BROKER_HOST,
        broker_port=MQTT_BROKER_PORT,
        username=MQTT_USERNAME,
        password=MQTT_PASSWORD,
    )

    try:
        client.connect()
    except ConnectionError as exc:
        logger.error("Fatal: could not connect to broker — %s", exc)
        sys.exit(1)

    client.loop_start()

    ppe_stub = PPEDetectionStub(client)
    env_stub = EnvSensorModule(client)
    nav_stub = NavigationStub(client, robot=robot)

    ppe_stub.start()
    env_stub.start()
    nav_stub.start()

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    logger.info("All modules running. Press Ctrl+C to stop.")
    while True:
        logger.info("System running | nav_state: %s", nav_stub.state)
        time.sleep(1)


if __name__ == "__main__":
    main()
