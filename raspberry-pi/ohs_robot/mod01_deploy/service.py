"""
service.py — MOD-01 Standalone Runner / Smoke-Test / Canlı Önizleme

MOD-03 olmadan bağımsız çalıştırır: kameradan frame alır, inference yapar, loglar.
Mac'te --preview ile canlı kamera + tespit kutularını pencerede gösterir.

Kullanım:
    python service.py                       # sürekli döngü, log modu (Ctrl+C ile dur)
    python service.py --once                # tek seferlik, latency raporlar
    python service.py --image test.jpg      # kamera yerine dosyadan (Pi'siz test)
    python service.py --preview             # Mac: canlı kamera penceresi + kutular (q ile kapat)
    python service.py --preview --interval 0  # en yüksek FPS
    PPE_LOG_LEVEL=DEBUG python service.py --preview

Pi üzerinde systemd ile çalışırken (--preview kullanılmaz):
    journalctl -u mod01-ppe -f
"""

import argparse
import signal
import sys
import time

from inference import (
    init, nav_waypoint_cb, ppe_run_inference,
    capture_frame, release_camera, draw_detections,
    VIOLATION_CLASSES,
)

_running = True


def _handle_signal(sig, frame):
    global _running
    print("\n[service] Durdurma sinyali alındı, çıkılıyor…")
    _running = False


def run(image_path=None, once=False, interval=5.0, preview=False):
    """
    Args:
        image_path: Belirtilirse kamera yerine bu dosya kullanılır.
        once:       True → tek inference, çık.
        interval:   Döngü aralığı (saniye). Preview modunda 0 önerilir.
        preview:    True → cv2.imshow ile canlı kamera penceresi (Mac).
    """
    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):   # Windows'ta SIGTERM yok
        signal.signal(signal.SIGTERM, _handle_signal)

    connect_mqtt = image_path is None   # dosyadan test ediliyorsa MQTT zorunlu değil
    init(connect_mqtt=connect_mqtt)

    print("[service] MOD-01 PPE Servisi başlatıldı.")
    if image_path:
        print(f"[service] Test modu: {image_path}")
    elif preview:
        print("[service] Önizleme modu — kamera açılıyor. Çıkmak için 'q' veya ESC.")
    else:
        print("[service] Kamera modu — PiCamera2 / OpenCV webcam.")

    # cv2.imshow erişilebilirliğini kontrol et
    _preview_ok = False
    if preview:
        try:
            import cv2 as _cv2_test
            _cv2_test.namedWindow("MOD-01 PPE", _cv2_test.WINDOW_NORMAL)
            _preview_ok = True
        except Exception as exc:
            print(f"[service] ⚠️  cv2.imshow kullanılamıyor ({exc}), log moduna geçildi.")
            preview = False

    latencies = []
    wp_counter = 0

    try:
        while _running:
            wp_counter += 1
            wp_id = f"smoke_wp_{wp_counter:04d}"

            if preview:
                # Önizleme: frame'i kendimiz alıp inference + çizim yapıyoruz
                import cv2
                frame = capture_frame()
                if frame is None:
                    print("[service] Kamera karesi alınamadı, çıkılıyor.")
                    break
                result = ppe_run_inference(frame=frame)
                if result["success"]:
                    vis = draw_detections(frame, result["detections"])
                    lat = result["latency_ms"]
                    # Pencere başlığına latency yaz
                    title = (
                        f"MOD-01 PPE  |  {lat:.0f}ms  |  "
                        f"tespit:{len(result['detections'])}  "
                        f"ihlal:{len(result['violations'])}"
                    )
                    cv2.setWindowTitle("MOD-01 PPE", title)
                    cv2.imshow("MOD-01 PPE", vis)
                    latencies.append(lat)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):   # q veya ESC
                    print("\n[service] Çıkış tuşu algılandı.")
                    break
            elif image_path:
                result = ppe_run_inference(image_path=image_path)
                _log_result(wp_id, result)
                if result["success"]:
                    latencies.append(result["latency_ms"])
            else:
                result = nav_waypoint_cb(waypoint_id=wp_id)
                _log_result(wp_id, result)
                if result["success"]:
                    latencies.append(result["latency_ms"])

            if once:
                break

            if interval > 0:
                time.sleep(interval)

    finally:
        release_camera()
        if _preview_ok:
            import cv2
            cv2.destroyAllWindows()

    _print_summary(latencies)


def _log_result(wp_id, result):
    """Log modunda tek inference sonucunu yazdırır."""
    if result["success"]:
        lat   = result["latency_ms"]
        viols = result["violations"]
        status = f"İHLAL ({len(viols)}x)" if viols else "temiz"
        print(
            f"[{wp_id}] {lat:6.1f}ms  {status}  "
            f"| tespitler: {len(result['detections'])}"
        )
        if viols:
            for v in viols:
                print(f"  ⚠️  {v['class']} conf={v['confidence']} box={v['bounding_box']}")
    else:
        print(f"[{wp_id}] inference başarısız")


def _print_summary(latencies):
    """Latency özeti."""
    if not latencies:
        return
    import numpy as np
    lat = np.array(latencies)
    print(f"\n{'='*50}")
    print(f"Çalıştırma özeti ({len(lat)} inference)")
    print(f"  Ortalama latency : {lat.mean():.1f} ms")
    print(f"  P95 latency      : {float(np.percentile(lat, 95)):.1f} ms")
    print(f"  Min/Max          : {lat.min():.1f} / {lat.max():.1f} ms")
    target = 500.0
    above  = (lat > target).sum()
    print(f"  Hedef <{target:.0f}ms    : {'✅ PASS' if above == 0 else f'⚠️  {above}/{len(lat)} hedef aşıyor'}")
    print(f"{'='*50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOD-01 PPE Service Runner")
    parser.add_argument("--once",    action="store_true", help="Tek inference çalıştır ve çık")
    parser.add_argument("--image",   default=None,        help="Test görsel dosyası (kamera yerine)")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Döngü aralığı saniye (varsayılan 5; preview için 0 önerilir)")
    parser.add_argument("--preview", action="store_true",
                        help="Canlı kamera önizleme penceresi (Mac; q ile çık)")
    args = parser.parse_args()

    run(
        image_path=args.image,
        once=args.once,
        interval=args.interval,
        preview=args.preview,
    )
