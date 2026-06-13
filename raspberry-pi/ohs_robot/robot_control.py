#!/usr/bin/env python3
# =====================================================================
#  OHS Robot - Raspberry Pi Kontrol & Reset Izleyici
# ---------------------------------------------------------------------
#  motor_control.ino ile haberlesir.
#   * Portu BIR KEZ acar ve acik tutar (tekrar tekrar acmak DTR reseti tetikler)
#   * Arka planda PING gonderir -> Arduino failsafe'i aktiflesir
#   * Arduino'dan gelen "READY"/"RESET_CAUSE" satirlarini izler:
#       - Beklenmedik bir READY gorunce "ARDUINO RESET OLDU" uyarisi basar
#       - Sebebi (BROWNOUT / EXTERNAL / WATCHDOG) ekrana yazar
#
#  Kurulum:   pip install pyserial
#  Calistir:  python3 robot_control.py
#
#  Komutlar (terminalden):
#     f 10        -> 10 saniye ileri
#     b 3         -> 3 saniye geri
#     l 1 / r 1   -> 1 saniye sol/sag
#     f           -> surekli ileri (s ile dur)
#     s           -> stop
#     speed 130   -> hizi ayarla (gucu kis)
#     trim -10 10 -> sol/sag denge
#     demo        -> ornek test dizisi (10sn ileri, dur, 3sn geri)
#     status / reset
#     q           -> cik
# =====================================================================

import sys
import time
import threading
import glob

try:
    import serial
except ImportError:
    print("pyserial yok. Kur:  pip install pyserial")
    sys.exit(1)


def find_port():
    """Arduino portunu otomatik bul."""
    candidates = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    return candidates[0] if candidates else None


class Robot:
    def __init__(self, port=None, baud=115200, heartbeat=0.5):
        self.port = port or find_port()
        if not self.port:
            raise RuntimeError("Arduino portu bulunamadi (/dev/ttyACM* veya /dev/ttyUSB*)")

        self.baud = baud
        self.heartbeat = heartbeat
        self.running = True
        self.ready_count = 0          # kac kez READY gorduk
        self._last_cause = None

        # NOT: pyserial portu acarken UNO'da DTR tetiklenir ve bir kez resetler.
        # Bu ILK reset normaldir. Onemli olan portu acik tutup tekrar acmamak.
        self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
        print(f"[i] Port acildi: {self.port} @ {self.baud}")
        print("[i] Arduino bootloader bekleniyor (~2 sn)...")
        time.sleep(2.0)               # bootloader + sketch baslamasi
        self.ser.reset_input_buffer()

        self._move_done = threading.Event()  # Arduino STOPPED gelince set edilir
        self.on_obstacle   = None   # callable(dist_cm: int)
        self.on_avoid_done = None   # callable()

        # okuyucu ve heartbeat thread'leri
        self._rx = threading.Thread(target=self._reader, daemon=True)
        self._hb = threading.Thread(target=self._heartbeater, daemon=True)
        self._rx.start()
        self._hb.start()

    # ----- gonder -----
    def send(self, line):
        try:
            self.ser.write((line.strip() + "\n").encode())
        except serial.SerialException as e:
            print(f"[!] Yazma hatasi: {e}")

    # ----- arka plan: heartbeat -----
    def _heartbeater(self):
        while self.running:
            self.send("PING")
            time.sleep(self.heartbeat)

    # ----- arka plan: okuyucu + reset izleyici -----
    def _reader(self):
        while self.running:
            try:
                raw = self.ser.readline()
            except serial.SerialException as e:
                print(f"[!] Okuma hatasi: {e}")
                break
            if not raw:
                continue
            line = raw.decode(errors="replace").strip()
            if not line or line == "PONG":
                continue

            if line.startswith("OBSTACLE"):
                try:
                    dist = int(line.split()[1].replace("cm", ""))
                except Exception:
                    dist = 0
                if callable(self.on_obstacle):
                    self.on_obstacle(dist)
                continue

            if line == "AVOID_DONE":
                if callable(self.on_avoid_done):
                    self.on_avoid_done()
                continue

            if line == "READY":
                self.ready_count += 1
                if self.ready_count > 1:
                    print("\n" + "=" * 50)
                    print("  !!! ARDUINO RESET OLDU !!!")
                    print("  (calisirken yeniden basladi - sebebi asagida)")
                    print("=" * 50)
                continue

            if line.startswith("RESET_CAUSE"):
                self._last_cause = line
                cause = line.replace("RESET_CAUSE", "").strip()
                if self.ready_count > 1:   # beklenmedik reset
                    self._explain_cause(cause)
                else:
                    print(f"[i] Acilis reset sebebi: {cause}")
                continue

            if line.startswith("STOPPED"):
                self._move_done.set()

            # normal Arduino mesajlari
            print(f"  < {line}")

    def _explain_cause(self, cause):
        print(f"  Sebep: {cause}")
        if "BROWNOUT" in cause:
            print("  -> GERILIM DUSTU. Motor kalkisinda akim cekildi, Arduino aclikta kaldi.")
            print("     COZUM: Arduino'yu motordan AYRI besle (ortak GND), buyuk")
            print("            kondansator (>=1000uF) ekle, ya da 'speed' ile gucu dusur.")
        elif "EXTERNAL" in cause:
            print("  -> DTR/reset. Genelde port yeniden acildi. Portu acik tut.")
            print("     Kalici cozum: RESET-GND arasi 10uF kondansator (yukleme sonrasi).")
        elif "WATCHDOG" in cause:
            print("  -> Kod kilitlendi, watchdog kurtardi. Firmware'de takilan yer var.")
        elif "POWERON" in cause:
            print("  -> Besleme kesilip geldi (guc dalgalanmasi / gevsek kablo).")

    # ----- yuksek seviye komutlar -----
    def forward(self, sec=0): self.send(f"FWD {int(sec*1000)}" if sec else "FWD")
    def back(self, sec=0):    self.send(f"BACK {int(sec*1000)}" if sec else "BACK")
    def left(self, sec=0):    self.send(f"LEFT {int(sec*1000)}" if sec else "LEFT")
    def right(self, sec=0):   self.send(f"RIGHT {int(sec*1000)}" if sec else "RIGHT")
    def stop(self):           self.send("STOP")
    def speed(self, v):       self.send(f"SPEED {int(v)}")
    def trim(self, l, r):     self.send(f"TRIM {int(l)} {int(r)}")
    def status(self):         self.send("STATUS")
    def reset_info(self):     self.send("RESETINFO")
    def dist(self):           self.send("DIST")
    def sonar(self, on=True): self.send("SONAR ON" if on else "SONAR OFF")

    def demo(self):
        print("[demo] 10 sn ileri")
        self.forward(10)
        time.sleep(11)
        print("[demo] 3 sn geri")
        self.back(3)
        time.sleep(4)
        print("[demo] bitti")

    def close(self):
        self.running = False
        time.sleep(0.3)
        try:
            self.stop()
            self.ser.close()
        except Exception:
            pass


HELP = """
Komutlar:
  f [sn]   ileri      (orn: f 10  ya da sadece f)
  b [sn]   geri
  l [sn]   sol
  r [sn]   sag
  s        stop
  speed v  hiz/guc ayarla (0-255)
  trim l r sol/sag denge (orn: trim -10 10)
  demo     ornek test
  status       durum
  reset        son reset sebebi
  dist         anlık sonar mesafesi
  sonar on/off engel kacınmayı ac/kapat
  h            bu yardim
  q            cik
"""


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        bot = Robot(port)
    except RuntimeError as e:
        print(f"[!] {e}")
        return

    print(HELP)
    try:
        while True:
            try:
                raw = input("> ").strip()
            except EOFError:
                break
            if not raw:
                continue
            parts = raw.split()
            c = parts[0].lower()
            try:
                arg = float(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                print(f"Gecersiz deger: '{parts[1]}'. Sayi girin. (orn: speed 150)")
                continue

            if   c == "q": break
            elif c == "h": print(HELP)
            elif c == "f": bot.forward(arg)
            elif c == "b": bot.back(arg)
            elif c == "l": bot.left(arg)
            elif c == "r": bot.right(arg)
            elif c == "s": bot.stop()
            elif c == "speed": bot.speed(arg)
            elif c == "trim" and len(parts) >= 3: bot.trim(parts[1], parts[2])
            elif c == "demo": bot.demo()
            elif c == "status": bot.status()
            elif c == "reset": bot.reset_info()
            elif c == "dist":  bot.dist()
            elif c == "sonar":
                on = len(parts) < 2 or parts[1].lower() in ("on", "1")
                bot.sonar(on)
            else: print("Bilinmeyen komut. 'h' yaz.")
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[i] Kapatiliyor, motorlar durduruluyor...")
        bot.close()


if __name__ == "__main__":
    main()
