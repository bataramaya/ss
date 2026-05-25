"""
╔══════════════════════════════════════════════════════════════════════╗
║   SIMULASI SENSOR AIR → THINGSPEAK                                  ║
║   Kondisi nyata: 25 ekor lele, bak tanpa sirkulasi                  ║
║   Dikuras seminggu sekali, cuaca Bandung real-time                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  Karakteristik simulasi:                                             ║
║  - Amonia terus naik karena tidak ada sirkulasi                     ║
║  - Makin mendekati hari kuras, amonia makin tinggi                  ║
║  - Suhu air dipengaruhi cuaca Bandung real-time                     ║
║  - TDS naik akibat akumulasi kotoran                                ║
║  - pH turun akibat akumulasi CO2 dan asam organik                   ║
╚══════════════════════════════════════════════════════════════════════╝
"""
 
import requests
import random
import math
import time
from datetime import datetime, timedelta
 
# ══════════════════════════════════════════════════════════════════════
#  KONFIGURASI
# ══════════════════════════════════════════════════════════════════════
WRITE_API_KEY  = "P3PP9Q26O82TB41R"
TS_URL         = "https://api.thingspeak.com/update.json"
INTERVAL       = 20  # detik
 
# ── Koordinat Bandung ─────────────────────────────────────────────────
LAT = -6.9175
LON = 107.6191
 
# ══════════════════════════════════════════════════════════════════════
#  PARAMETER BAK LELE
#  Asumsi bak ukuran 1m x 2m x 0.5m = 1000 liter
#  25 ekor lele ukuran 10-15cm (~30 gram/ekor)
#  Tanpa aerasi, tanpa sirkulasi, tanpa filter
# ══════════════════════════════════════════════════════════════════════
JUMLAH_LELE     = 25
BERAT_LELE_GRAM = 30        # gram per ekor rata-rata
VOLUME_BAK_L    = 1000      # liter
PORSI_PAKAN_PCT = 3         # % dari berat tubuh per hari (standar lele)
 
# Jam kuras terakhir (simulasi: bak dikuras hari ini jam 06.00)
# Ubah ini sesuai kapan terakhir kuras
KURAS_TERAKHIR = datetime.now().replace(
    hour=6, minute=0, second=0, microsecond=0
)
# Kalau jam sekarang sebelum jam 06, anggap kuras kemarin
if datetime.now() < KURAS_TERAKHIR:
    KURAS_TERAKHIR -= timedelta(days=1)
 
INTERVAL_KURAS_HARI = 7     # dikuras tiap 7 hari
 
 
# ══════════════════════════════════════════════════════════════════════
#  CUACA BANDUNG REAL-TIME (Open-Meteo, cache 10 menit)
# ══════════════════════════════════════════════════════════════════════
cuaca_cache = {
    "suhu_udara" : 22.0,
    "kelembaban" : 80.0,
    "hujan"      : 0.0,
    "radiasi"    : 0.0,
    "last_update": 0,
}
 
def ambil_cuaca():
    now = time.time()
    if now - cuaca_cache["last_update"] < 600:
        return cuaca_cache
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            "&current=temperature_2m,relative_humidity_2m,"
            "precipitation,shortwave_radiation"
            "&timezone=Asia%2FJakarta"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            c = r.json().get("current", {})
            cuaca_cache["suhu_udara"]  = c.get("temperature_2m", 22.0)
            cuaca_cache["kelembaban"]  = c.get("relative_humidity_2m", 80.0)
            cuaca_cache["hujan"]       = c.get("precipitation", 0.0)
            cuaca_cache["radiasi"]     = c.get("shortwave_radiation", 0.0)
            cuaca_cache["last_update"] = now
            print(f"\n[Cuaca Bandung] "
                  f"Udara={cuaca_cache['suhu_udara']}°C | "
                  f"Lembab={cuaca_cache['kelembaban']}% | "
                  f"Hujan={cuaca_cache['hujan']}mm | "
                  f"Radiasi={cuaca_cache['radiasi']}W/m²")
    except Exception as e:
        print(f"[Cuaca] Gagal ambil data: {e}, pakai cache.")
    return cuaca_cache
 
 
# ══════════════════════════════════════════════════════════════════════
#  HITUNG HARI SEJAK KURAS
#  Makin lama tidak dikuras → amonia, TDS makin tinggi, pH makin turun
# ══════════════════════════════════════════════════════════════════════
def hari_sejak_kuras():
    delta = datetime.now() - KURAS_TERAKHIR
    hari  = delta.total_seconds() / 86400  # dalam desimal hari
    return min(hari, INTERVAL_KURAS_HARI)  # max 7 hari
 
def faktor_akumulasi():
    """
    Faktor 0.0 - 1.0
    0.0 = baru dikuras (air bersih)
    1.0 = hari ke-7 (air sangat kotor, perlu kuras)
    """
    return hari_sejak_kuras() / INTERVAL_KURAS_HARI
 
 
# ══════════════════════════════════════════════════════════════════════
#  SUHU AIR BAK LELE
#  Bak tertutup/semi-terbuka → lebih terpengaruh suhu udara
#  Volume kecil (1000L) → suhu berubah lebih cepat dari kolam besar
# ══════════════════════════════════════════════════════════════════════
suhu_state = {"nilai": None}
 
def hitung_suhu(cuaca):
    suhu_udara = cuaca["suhu_udara"]
    radiasi    = cuaca["radiasi"]
    hujan      = cuaca["hujan"]
 
    # Bak kecil lebih cepat mengikuti suhu udara
    # + efek radiasi matahari langsung ke bak
    efek_radiasi = (radiasi / 100.0) * 0.2
    efek_hujan   = -hujan * 0.15  # hujan Bandung ~19°C, turunkan suhu bak
 
    # Bak tanpa sirkulasi → panas terkurung
    efek_tanpa_sirkulasi = 1.5  # lebih panas 1.5°C dari kolam biasa
 
    target = suhu_udara + efek_tanpa_sirkulasi + efek_radiasi + efek_hujan
    target = max(18.0, min(35.0, target))
 
    if suhu_state["nilai"] is None:
        suhu_state["nilai"] = target
 
    # Bak kecil → suhu berubah lebih cepat (alpha lebih besar dari kolam)
    suhu_state["nilai"] += (target - suhu_state["nilai"]) * 0.005
    noise = random.gauss(0, 0.08)
    return round(suhu_state["nilai"] + noise, 2)
 
 
# ══════════════════════════════════════════════════════════════════════
#  AMONIA (NH3) — KUNCI UTAMA SIMULASI INI
#
#  Sumber amonia di bak lele tanpa sirkulasi:
#  1. Ekskresi lele langsung (urin + insang) → terus-menerus
#  2. Sisa pakan yang membusuk → spike setelah pakan
#  3. Kotoran lele (feses) terdekomposisi → akumulasi harian
#  4. Tidak ada filter/sirkulasi → amonia tidak terurai
#
#  Produksi amonia lele:
#  ~10mg NH3 per gram pakan per hari (standar penelitian)
#  25 ekor × 30g × 3% pakan = 22.5g pakan/hari
#  22.5g × 10mg/g = 225mg NH3/hari
#  Volume 1000L → 0.225 ppm/hari akumulasi
#
#  Artinya:
#  Hari 1: ~0.2 ppm
#  Hari 3: ~0.6 ppm (mulai berbahaya)
#  Hari 7: ~1.5 ppm (sangat berbahaya)
# ══════════════════════════════════════════════════════════════════════
NH3_PRODUKSI_PER_HARI = (
    JUMLAH_LELE * BERAT_LELE_GRAM * (PORSI_PAKAN_PCT/100) * 10
) / VOLUME_BAK_L / 1000  # konversi mg→ppm
 
nh3_state = {"nilai": None, "tren": 0.0}
 
def hitung_nh3(jam_desimal, suhu, cuaca):
    akumulasi = faktor_akumulasi()
    hujan     = cuaca["hujan"]
    radiasi   = cuaca["radiasi"]
 
    # ── Base NH3 berdasarkan hari sejak kuras ──────────────────────────
    # Makin lama → makin tinggi akumulasi kotoran
    # Kurva naik tidak linear (bakteri makin banyak di hari akhir)
    nh3_base = NH3_PRODUKSI_PER_HARI * hari_sejak_kuras() * (1 + akumulasi * 0.5)
 
    # ── Pola harian (subuh tinggi, siang turun) ────────────────────────
    fase     = (jam_desimal - 5.0) / 24.0 * 2.0 * math.pi
    pola_hari = nh3_base * 0.2 * (-math.cos(fase))  # ±20% dari base
 
    # ── Pengaruh suhu (makin panas → NH3 bebas makin toksik) ───────────
    faktor_suhu = 1.0 + 0.05 * (suhu - 24.0)
 
    # ── Spike setelah pakan (jam 07.00 dan 17.00) ──────────────────────
    # Lele rakus → banyak sisa pakan → amonia cepat naik
    spike = 0.0
    for jam_pakan in [7.0, 17.0]:
        selisih = jam_desimal - jam_pakan
        if 0 <= selisih <= 2.0:
            menit = selisih * 60
            besar_spike = nh3_base * 0.4  # spike 40% dari nilai base
            if menit <= 25:
                spike += besar_spike * (menit / 25)
            else:
                spike += besar_spike * math.exp(-(menit - 25) / 35)
 
    # ── Efek hujan (encerkan sedikit) ──────────────────────────────────
    efek_hujan = -hujan * 0.02
 
    # ── Efek radiasi (fotosintesis alga, minimal di bak) ───────────────
    # Bak biasanya kurang cahaya → alga sedikit → efek kecil
    efek_radiasi = -(radiasi / 800.0) * 0.02
 
    # ── Tren biologis acak ─────────────────────────────────────────────
    nh3_state["tren"] += random.gauss(0, 0.0003)
    nh3_state["tren"]  = max(-0.02, min(0.02, nh3_state["tren"]))
 
    target = ((nh3_base + pola_hari + spike +
               efek_hujan + efek_radiasi + nh3_state["tren"])
              * faktor_suhu)
    target = max(0.01, min(5.0, target))
 
    if nh3_state["nilai"] is None:
        nh3_state["nilai"] = target
 
    # Bak kecil → amonia berubah lebih cepat dari kolam besar
    nh3_state["nilai"] += (target - nh3_state["nilai"]) * 0.005
    noise = random.gauss(0, nh3_base * 0.02)
    return round(max(0.01, nh3_state["nilai"] + noise), 4)
 
 
# ══════════════════════════════════════════════════════════════════════
#  STATUS & PERINGATAN
# ══════════════════════════════════════════════════════════════════════
def status_nh3(ppm, hari):
    if ppm < 0.1:    return "✅ Aman"
    elif ppm < 0.3:  return "⚠️  Waspada"
    elif ppm < 0.5:  return "🔴 Berbahaya"
    elif ppm < 1.0:  return "🔴 KRITIS"
    else:            return "💀 DARURAT"
 
def status_suhu(c):
    if 26 <= c <= 30: return "✅ Optimal lele"
    elif c < 26:      return "⚠️  Terlalu dingin"
    elif c > 32:      return "🔴 Terlalu panas"
    else:             return "⚠️  Agak panas"
 
def peringatan_kuras(hari):
    sisa = INTERVAL_KURAS_HARI - hari
    if sisa <= 0:
        return "💀 HARUS KURAS SEKARANG!"
    elif sisa < 1:
        return f"🔴 Kuras dalam {sisa*24:.0f} jam!"
    elif sisa < 2:
        return f"⚠️  Kuras dalam {sisa:.1f} hari"
    else:
        return f"✅ Sisa {sisa:.1f} hari sebelum kuras"
 
 
# ══════════════════════════════════════════════════════════════════════
#  KIRIM KE THINGSPEAK
# ══════════════════════════════════════════════════════════════════════
def kirim(nh3, suhu):
    try:
        r = requests.post(TS_URL, json={
            "api_key": WRITE_API_KEY,
            "field1" : str(nh3),
            "field2" : str(suhu),
        }, headers={"Content-Type": "application/json"}, timeout=15)
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
    print("=" * 70)
    print("  SIMULASI BAK LELE → THINGSPEAK")
    print("  25 ekor lele | Bak 1000L | Tanpa sirkulasi | Kuras 7 hari")
    print("  Cuaca: Bandung real-time (Open-Meteo)")
    print("=" * 70)
    print(f"  Kuras terakhir : {KURAS_TERAKHIR.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Produksi NH3   : ~{NH3_PRODUKSI_PER_HARI*1000:.2f} mg/L per hari")
    print(f"  Perkiraan NH3  :")
    for h in [1, 2, 3, 5, 7]:
        est = NH3_PRODUKSI_PER_HARI * h * 1.25
        print(f"    Hari {h}: ~{est:.3f} ppm", end="")
        if est > 0.5: print(" ⚠️ BERBAHAYA")
        elif est > 0.3: print(" ⚠️ Waspada")
        else: print(" ✅ Aman")
    print("=" * 70)
    print("  Tekan Ctrl+C untuk berhenti\n")
 
    total = 0
    gagal = 0
 
    while True:
        now       = datetime.now()
        jam       = now.hour + now.minute / 60 + now.second / 3600
        waktu_str = now.strftime("%H:%M:%S")
        hari      = hari_sejak_kuras()
 
        cuaca = ambil_cuaca()
        suhu  = hitung_suhu(cuaca)
        nh3   = hitung_nh3(jam, suhu, cuaca)
 
        sukses, info = kirim(nh3, suhu)
        total += 1
 
        baris = (
            f"[{waktu_str}] "
            f"Hari ke-{hari:.2f} | "
            f"NH3={nh3:.4f}ppm {status_nh3(nh3, hari):15} | "
            f"Suhu={suhu:.2f}C {status_suhu(suhu):18} | "
            f"{peringatan_kuras(hari):30} | "
        )
        if sukses:
            print(baris + f"OK #{info}")
        else:
            gagal += 1
            print(baris + f"GAGAL [{info}]")
 
        try:
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print(f"\n{'=' * 70}")
            print(f"  Dihentikan.")
            print(f"  Total={total} | OK={total-gagal} | Gagal={gagal}")
            print(f"{'=' * 70}")
            break
 
if __name__ == "__main__":
    main()
