"""
Simulasi Data Sensor → ThingSpeak
NH3 + Suhu Air — Realistis 24 Jam Penuh
Deploy di Railway.app
"""

import requests
import random
import math
import time
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════
#  KONFIGURASI
# ══════════════════════════════════════════════════════════════════════
WRITE_API_KEY = "P3PP9Q26O82TB41R"
TS_URL        = "https://api.thingspeak.com/update"
INTERVAL      = 20  # detik antar kirim (minimum 15)

# ══════════════════════════════════════════════════════════════════════
#  SIMULASI SUHU AIR
#  - Dingin jam 04.00-05.00 subuh (~26°C)
#  - Panas  jam 13.00-15.00 siang (~31°C)
# ══════════════════════════════════════════════════════════════════════
def hitung_suhu(jam_desimal):
    fase = (jam_desimal - 4) / 24 * 2 * math.pi
    suhu = 28.0 + 2.5 * math.sin(fase) + random.gauss(0, 0.15)
    return round(max(24.0, min(34.0, suhu)), 2)

# ══════════════════════════════════════════════════════════════════════
#  SIMULASI AMONIA (NH3)
#  - Tinggi subuh  (bakteri nitrifikasi tidak aktif)
#  - Turun siang   (fotosintesis alga menyerap NH3)
#  - Spike jam 07.00 & 17.00 (setelah pakan)
#  - Suhu tinggi = amonia lebih tinggi
# ══════════════════════════════════════════════════════════════════════
nh3_state = {"nilai": 0.15, "tren": 0.0}

def hitung_nh3(jam_desimal, suhu):
    fase_nh3    = (jam_desimal - 5) / 24 * 2 * math.pi
    pola_hari   = 0.10 * (-math.cos(fase_nh3))
    faktor_suhu = 1.0 + 0.07 * (suhu - 28.0)

    spike = 0.0
    if (6.9 < jam_desimal < 7.5) or (16.9 < jam_desimal < 17.5):
        menit_lewat = (jam_desimal % 1) * 60
        spike = 0.08 * math.exp(-((menit_lewat - 5) ** 2) / 30)

    noise = random.gauss(0, 0.008)
    nh3_state["tren"] += random.gauss(0, 0.001)
    nh3_state["tren"]  = max(-0.02, min(0.02, nh3_state["tren"]))

    target = (0.15 + pola_hari + spike + nh3_state["tren"] + noise) * faktor_suhu
    target = max(0.005, min(1.5, target))

    nh3_state["nilai"] += (target - nh3_state["nilai"]) * 0.25
    return round(nh3_state["nilai"], 4)

# ══════════════════════════════════════════════════════════════════════
#  STATUS
# ══════════════════════════════════════════════════════════════════════
def status_nh3(ppm):
    if ppm < 0.05:   return "Sangat Baik"
    elif ppm < 0.1:  return "Normal"
    elif ppm < 0.3:  return "Waspada"
    elif ppm < 0.5:  return "Berbahaya"
    else:            return "KRITIS"

def status_suhu(c):
    if 26 <= c <= 30:  return "Optimal"
    elif c < 26:       return "Terlalu Dingin"
    elif c > 32:       return "Berbahaya"
    else:              return "Terlalu Panas"

# ══════════════════════════════════════════════════════════════════════
#  KIRIM KE THINGSPEAK
# ══════════════════════════════════════════════════════════════════════
def kirim(nh3, suhu):
    try:
        r = requests.get(TS_URL, params={
            "api_key": WRITE_API_KEY,
            "field1" : nh3,
            "field2" : suhu,
        }, timeout=10)
        if r.status_code == 200 and r.text.strip() not in ("0", ""):
            return True, int(r.text.strip())
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Tidak ada koneksi"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

# ══════════════════════════════════════════════════════════════════════
#  MAIN — jalan terus tanpa batas (Railway mengelola prosesnya)
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  Simulasi Sensor Air → ThingSpeak")
    print(f"  Mulai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Interval: {INTERVAL} detik")
    print("  Mode: 24 JAM PENUH (Railway worker)")
    print("=" * 60)

    total = 0
    gagal = 0

    while True:
        now         = datetime.now()
        jam         = now.hour + now.minute / 60 + now.second / 3600
        waktu_str   = now.strftime("%H:%M:%S")

        suhu = hitung_suhu(jam)
        nh3  = hitung_nh3(jam, suhu)

        sukses, info = kirim(nh3, suhu)
        total += 1

        if sukses:
            gagal_pct = (gagal / total * 100) if total > 0 else 0
            print(f"[{waktu_str}] NH3={nh3:.4f}ppm ({status_nh3(nh3)}) | "
                  f"Suhu={suhu:.2f}C ({status_suhu(suhu)}) | "
                  f"OK #{info} | total={total} gagal={gagal_pct:.1f}%")
        else:
            gagal += 1
            print(f"[{waktu_str}] GAGAL [{info}] | total={total}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
