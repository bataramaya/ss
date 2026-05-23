"""
Simulasi Data Sensor → ThingSpeak
NH3 + Suhu Air — Ritme REALISTIS sesuai lapangan
- Suhu berubah sangat lambat (massa air besar)
- Amonia berubah perlahan (proses biologis)
- Spike pakan naik 15-30 menit, turun 1-2 jam
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
TS_URL        = "https://api.thingspeak.com/update.json"
INTERVAL      = 20  # detik antar kirim

# ══════════════════════════════════════════════════════════════════════
#  SIMULASI SUHU — SANGAT LAMBAT (massa air besar)
#
#  Siklus 24 jam nyata:
#  04.00 = 26.0°C (paling dingin)
#  14.00 = 31.0°C (paling panas)
#  Perubahan ~0.0014°C per detik = 5°C dalam 1 jam
# ══════════════════════════════════════════════════════════════════════
suhu_state = {"nilai": None}

def hitung_suhu(jam_desimal):
    # Target suhu berdasarkan jam (siklus sinus 24 jam)
    # Puncak panas jam 14.00, paling dingin jam 04.00
    fase   = (jam_desimal - 4.0) / 24.0 * 2.0 * math.pi
    target = 28.0 + 2.5 * math.sin(fase)
    target = max(24.0, min(34.0, target))

    # Inisialisasi pertama
    if suhu_state["nilai"] is None:
        suhu_state["nilai"] = target

    # Smoothing sangat lambat — 0.001 per tick (20 detik)
    # Artinya perubahan 1°C butuh ~1000 tick = ~333 menit ≈ 5.5 jam
    # Lebih realistis untuk massa air kolam besar
    alpha = 0.001
    suhu_state["nilai"] += (target - suhu_state["nilai"]) * alpha

    # Tambah noise kecil sensor (±0.05°C)
    noise = random.gauss(0, 0.05)
    return round(suhu_state["nilai"] + noise, 2)


# ══════════════════════════════════════════════════════════════════════
#  SIMULASI AMONIA — LAMBAT (proses biologis)
#
#  Pola harian nyata:
#  - Subuh (04-06): paling tinggi ~0.25 ppm
#  - Siang (12-14): paling rendah ~0.05 ppm
#  - Naik lagi malam: ~0.15 ppm
#  - Spike setelah pakan: naik 0.1 ppm dalam 20 menit,
#    turun kembali dalam 1-2 jam
# ══════════════════════════════════════════════════════════════════════
nh3_state = {"nilai": None, "tren": 0.0}

def hitung_nh3(jam_desimal, suhu):
    # Target berdasarkan pola harian
    # Puncak subuh jam 05, rendah jam 13
    fase_nh3  = (jam_desimal - 5.0) / 24.0 * 2.0 * math.pi
    pola_hari = 0.10 * (-math.cos(fase_nh3))

    # Pengaruh suhu (kimia nyata: suhu tinggi = NH3 bebas lebih banyak)
    faktor_suhu = 1.0 + 0.05 * (suhu - 28.0)

    # Spike setelah pakan jam 07.00 dan 17.00
    # Naik dalam 20 menit, turun dalam 90 menit
    spike = 0.0
    for jam_pakan in [7.0, 17.0]:
        selisih_jam = jam_desimal - jam_pakan
        if 0 <= selisih_jam <= 2.0:  # dalam 2 jam setelah pakan
            # Naik cepat 20 menit pertama, turun lambat sampai 2 jam
            selisih_menit = selisih_jam * 60
            if selisih_menit <= 20:
                spike += 0.10 * (selisih_menit / 20)  # naik linear
            else:
                spike += 0.10 * math.exp(-(selisih_menit - 20) / 40)  # turun eksponensial

    # Tren biologis acak sangat lambat
    nh3_state["tren"] += random.gauss(0, 0.0002)
    nh3_state["tren"]  = max(-0.01, min(0.01, nh3_state["tren"]))

    target = (0.10 + pola_hari + spike + nh3_state["tren"]) * faktor_suhu
    target = max(0.005, min(1.0, target))

    # Inisialisasi pertama
    if nh3_state["nilai"] is None:
        nh3_state["nilai"] = target

    # Smoothing lambat — proses biologis tidak instan
    # 0.002 per tick = perubahan 0.1 ppm butuh ~50 tick = ~17 menit
    alpha = 0.002
    nh3_state["nilai"] += (target - nh3_state["nilai"]) * alpha

    # Noise kecil sensor (±0.002 ppm)
    noise = random.gauss(0, 0.002)
    return round(max(0.001, nh3_state["nilai"] + noise), 4)


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
        payload = {
            "api_key": WRITE_API_KEY,
            "field1" : str(nh3),
            "field2" : str(suhu),
        }
        r = requests.post(
            TS_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        if r.status_code == 200 and r.text.strip() not in ("0", ""):
            return True, r.text.strip()
        return False, f"HTTP {r.status_code} body={r.text.strip()[:30]}"
    except requests.exceptions.ConnectionError:
        return False, "Tidak ada koneksi"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 65)
    print("  Simulasi Sensor Air → ThingSpeak")
    print(f"  Mulai  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  API    : {WRITE_API_KEY}")
    print(f"  Interval: {INTERVAL} detik")
    print()
    print("  Ritme realistis:")
    print("  Suhu  → berubah sangat lambat (~5°C dalam 5-6 jam)")
    print("  NH3   → berubah lambat, spike 20 menit setelah pakan")
    print("          (jam 07.00 dan 17.00)")
    print("=" * 65)

    total = 0
    gagal = 0

    while True:
        now       = datetime.now()
        jam       = now.hour + now.minute / 60 + now.second / 3600
        waktu_str = now.strftime("%H:%M:%S")

        suhu = hitung_suhu(jam)
        nh3  = hitung_nh3(jam, suhu)

        sukses, info = kirim(nh3, suhu)
        total += 1

        if sukses:
            print(f"[{waktu_str}] "
                  f"NH3={nh3:.4f}ppm ({status_nh3(nh3):11}) | "
                  f"Suhu={suhu:.2f}C ({status_suhu(suhu):14}) | "
                  f"OK #{info} | total={total} gagal={gagal}")
        else:
            gagal += 1
            print(f"[{waktu_str}] GAGAL [{info}] | total={total} gagal={gagal}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()

