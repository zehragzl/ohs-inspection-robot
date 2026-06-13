"""
MOD-01 PC Kamera + MQTT Test
Tek inference çalıştırır, MQTT'ye publish eder ve sonuçları gösterir.
"""

import json
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mod01_deploy"))

import paho.mqtt.client as mqtt

received_messages = []

def listen_mqtt(timeout=10):
    """ohs/ppe/violation topicini dinler."""
    result = []

    def on_message(client, userdata, msg):
        data = json.loads(msg.payload.decode())
        result.append(data)
        print(f"\n[MQTT] Mesaj alındı → topic: {msg.topic}")
        print(f"       {json.dumps(data, indent=2, ensure_ascii=False)}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect("localhost", 1883, 60)
    client.subscribe("ohs/ppe/violation")
    client.loop_start()
    return client, result


def main():
    print("=" * 55)
    print("  MOD-01 PC Kamera + MQTT Testi")
    print("=" * 55)

    # MQTT dinleyici başlat
    print("\n[1] MQTT dinleyici başlatılıyor (localhost:1883)...")
    mqtt_client, mqtt_received = listen_mqtt()
    time.sleep(0.5)  # bağlantı kurulsun

    # inference.py'yi yükle
    print("[2] Model yükleniyor...")
    from inference import init, ppe_run_inference, capture_frame, release_camera

    init(connect_mqtt=True)
    time.sleep(1)  # MQTT bağlantısı kurulsun

    # PC kamerasından frame al
    print("[3] PC kamerasından frame alınıyor (index=0)...")
    frame = capture_frame()

    if frame is None:
        print("\n[HATA] Kamera açılamadı!")
        print("  → PPE_CAMERA_INDEX=1 python3 test_mod01_mqtt.py  ile farklı index deneyin.")
        release_camera()
        mqtt_client.loop_stop()
        return

    print(f"      Frame boyutu: {frame.shape[1]}x{frame.shape[0]} piksel")

    # Inference
    print("[4] Inference çalıştırılıyor...")
    result = ppe_run_inference(frame=frame)

    print(f"\n[SONUÇ] {'='*45}")
    if result["success"]:
        print(f"  Latency   : {result['latency_ms']} ms")
        print(f"  Tespitler : {len(result['detections'])}")
        print(f"  İhlaller  : {len(result['violations'])}")
        for d in result["detections"]:
            tag = "⚠ İHLAL" if d["class_id"] in {1, 3, 5} else "  OK    "
            print(f"    {tag} | {d['class']:20s} conf={d['confidence']:.3f}")
    else:
        print("  Inference başarısız!")

    # MQTT mesajı bekleniyor
    print(f"\n[5] MQTT mesajı bekleniyor (2 sn)...")
    time.sleep(2)

    if mqtt_received:
        print(f"\n✅ MQTT ÇALIŞIYOR — {len(mqtt_received)} ihlal mesajı publish edildi.")
    elif result["violations"]:
        print("\n⚠  İhlal tespit edildi ama MQTT mesajı gelmedi — broker bağlantısını kontrol edin.")
    else:
        print("\n✅ İhlal yok — MQTT mesajı gönderilmedi (beklenen davranış).")

    release_camera()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    print("\nTest tamamlandı.")


if __name__ == "__main__":
    main()
