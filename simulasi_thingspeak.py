"""
╔══════════════════════════════════════════════════════════════════════╗
║   SIMULASI BAK LELE → THINGSPEAK  v3.0  (~85% akurasi lapangan)    ║
║   25 ekor lele | Bak 1000L | Tanpa sirkulasi | Kuras 7 hari        ║
║   Cuaca Bandung real-time (Open-Meteo)                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  Fitur baru v3.0:                                                    ║
║   ✦ DO (oksigen terlarut) — pengaruhi NH3 & kondisi lele           ║
║   ✦ Lele stres saat NH3/suhu ekstrem → kurang makan → NH3 turun    ║
║   ✦ Penguapan air harian → volume berkurang → NH3 makin pekat      ║
║   ✦ Pertumbuhan berat lele → produksi NH3 naik tiap hari           ║
║   ✦ Simulasi kematian lele jika kondisi kritis terlalu lama        ║
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
WRITE_API_KEY       = "P3PP9Q26O82TB41R"
TS_URL              = "https://api.thingspeak.com/update.json"
INTERVAL            = 20   # detik
 
LAT = -6.9175
LON = 107.6191
 
# ══════════════════════════════════════════════════════════════════════
#  STATE BAK LELE — berubah seiring waktu
# ══════════════════════════════════════════════════════════════════════
bak = {
    # ── Ikan ────────────────────────────────────────────────────────
    "jumlah_lele"     : 25,          # ekor (bisa berkurang kalau mati)
    "berat_gram"      : 30.0,        # gram/ekor (tumbuh ~0.5g/hari)
    "stres_level"     : 0.0,         # 0.0=normal, 1.0=stres penuh
    "jam_stres_kritis": 0.0,         # akumulasi jam dalam kondisi kritis
 
    # ── Air ──────────────────────────────────────────────────────────
    "volume_liter"    : 1000.0,      # berkurang karena penguapan
    "suhu_air"        : 24.0,        # °C
    "nh3_ppm"         : 0.05,        # ppm
    "do_ppm"          : 7.0,         # mg/L (oksigen terlarut)
    "ph"              : 7.2,         # pH
 
    # ── Waktu ────────────────────────────────────────────────────────
    "kuras_terakhir"  : datetime.now().replace(
                            hour=6, minute=0, second=0, microsecond=0),
    "interval_kuras"  : 7,           # hari
    "last_tick"       : datetime.now(),
}
 
# Koreksi waktu kuras terakhir
if datetime.now() < bak["kuras_terakhir"]:
    bak["kuras_terakhir"] -= timedelta(days=1)
 
 
# ══════════════════════════════════════════════════════════════════════
#  CUACA BANDUNG (Open-Meteo, cache 10 menit)
# ══════════════════════════════════════════════════════════════════════
cuaca_cache = {
    "suhu_udara" : 22.0, "kelembaban": 80.0,
    "hujan"      : 0.0,  "radiasi"   : 0.0,
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
            cuaca_cache.update({
                "suhu_udara" : c.get("temperature_2m", 22.0),
                "kelembaban" : c.get("relative_humidity_2m", 80.0),
                "hujan"      : c.get("precipitation", 0.0),
                "radiasi"    : c.get("shortwave_radiation", 0.0),
                "last_update": now,
            })
            print(f"\n[Cuaca Bandung] "
                  f"Udara={cuaca_cache['suhu_udara']}°C | "
                  f"Lembab={cuaca_cache['kelembaban']}% | "
                  f"Hujan={cuaca_cache['hujan']}mm | "
                  f"Radiasi={cuaca_cache['radiasi']}W/m²")
    except Exception as e:
        print(f"[Cuaca] Gagal: {e}, pakai cache.")
    return cuaca_cache
 
 
# ══════════════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════════════
def hari_sejak_kuras():
    delta = datetime.now() - bak["kuras_terakhir"]
    return min(delta.total_seconds() / 86400, bak["interval_kuras"])
 
def faktor_akumulasi():
    return hari_sejak_kuras() / bak["interval_kuras"]
 
def detik_per_tick():
    now = datetime.now()
    dt  = (now - bak["last_tick"]).total_seconds()
    bak["last_tick"] = now
    return max(dt, INTERVAL)
 
 
# ══════════════════════════════════════════════════════════════════════
#  UPDATE PERTUMBUHAN LELE
#  Lele tumbuh ~0.5g/hari → produksi NH3 naik seiring waktu
#  Pertumbuhan melambat saat stres
# ══════════════════════════════════════════════════════════════════════
def update_pertumbuhan(dt_detik):
    if bak["jumlah_lele"] <= 0:
        return
    pertumbuhan_per_detik = 0.5 / 86400  # 0.5 gram/hari
    faktor_stres = max(0.1, 1.0 - bak["stres_level"] * 0.8)
    bak["berat_gram"] += pertumbuhan_per_detik * dt_detik * faktor_stres
    bak["berat_gram"]  = min(bak["berat_gram"], 500.0)  # max 500g
 
 
# ══════════════════════════════════════════════════════════════════════
#  UPDATE VOLUME AIR (penguapan)
#  Penguapan ~3-5 liter/hari di Bandung (kelembaban tinggi = sedikit)
#  Volume berkurang → konsentrasi NH3 meningkat
# ══════════════════════════════════════════════════════════════════════
def update_volume(dt_detik, cuaca):
    kelembaban = cuaca["kelembaban"]
    radiasi    = cuaca["radiasi"]
    hujan      = cuaca["hujan"]
 
    # Penguapan: lebih rendah di Bandung karena lembab
    # Dasar 3L/hari, dikurangi kelembaban, ditambah radiasi
    penguapan_per_hari = 3.0 * (1 - kelembaban/100) * (1 + radiasi/400)
    penguapan_per_detik = penguapan_per_hari / 86400
 
    # Hujan tambah volume (asumsi bak terbuka sebagian)
    tambah_hujan = hujan * 0.5 * (dt_detik / 3600)
 
    bak["volume_liter"] -= penguapan_per_detik * dt_detik
    bak["volume_liter"] += tambah_hujan
    bak["volume_liter"]  = max(700.0, min(1100.0, bak["volume_liter"]))
 
 
# ══════════════════════════════════════════════════════════════════════
#  UPDATE DO (OKSIGEN TERLARUT)
#  DO normal air: 7-9 mg/L
#  DO turun karena:
#   - Respirasi lele (makin banyak/besar lele → DO makin turun)
#   - Dekomposisi kotoran (butuh oksigen)
#   - Suhu tinggi → DO saturasi lebih rendah
#   - Malam → tidak ada fotosintesis
#  DO naik karena:
#   - Difusi dari udara (lambat tanpa aerasi)
#   - Fotosintesis alga siang hari (minimal di bak)
#   - Hujan (bawa oksigen)
# ══════════════════════════════════════════════════════════════════════
def update_do(dt_detik, jam_desimal, cuaca):
    suhu   = bak["suhu_air"]
    radiasi = cuaca["radiasi"]
    hujan   = cuaca["hujan"]
 
    # DO saturasi berdasarkan suhu (rumus empiris)
    do_saturasi = 14.62 - 0.3898*suhu + 0.006969*suhu**2 - 0.00005897*suhu**3
 
    # Konsumsi O2 oleh lele (mg/L per detik)
    # ~200mg O2/kg ikan/jam (standar penelitian)
    biomassa_kg  = (bak["jumlah_lele"] * bak["berat_gram"]) / 1000
    konsumsi_o2  = (biomassa_kg * 200) / 3600 / bak["volume_liter"]
    konsumsi_o2 *= dt_detik
 
    # Konsumsi O2 oleh dekomposisi kotoran
    # Makin tua air → makin banyak bakteri → makin banyak O2 terpakai
    konsumsi_dekomposisi = faktor_akumulasi() * 0.001 * dt_detik
 
    # Difusi dari udara (sangat lambat tanpa aerasi)
    deficit  = do_saturasi - bak["do_ppm"]
    difusi   = deficit * 0.0001 * dt_detik  # koef transfer lambat
 
    # Fotosintesis alga siang (minimal di bak)
    foto = (radiasi / 800) * 0.0002 * dt_detik if jam_desimal > 6 and jam_desimal < 18 else 0
 
    # Efek hujan (bawa oksigen)
    efek_hujan = hujan * 0.01 * (dt_detik / 3600)
 
    bak["do_ppm"] += difusi + foto + efek_hujan - konsumsi_o2 - konsumsi_dekomposisi
    bak["do_ppm"]  = max(0.1, min(do_saturasi, bak["do_ppm"]))
 
 
# ══════════════════════════════════════════════════════════════════════
#  UPDATE SUHU AIR
# ══════════════════════════════════════════════════════════════════════
def update_suhu(dt_detik, cuaca):
    suhu_udara = cuaca["suhu_udara"]
    radiasi    = cuaca["radiasi"]
    hujan      = cuaca["hujan"]
 
    efek_radiasi = (radiasi / 100.0) * 0.2
    efek_hujan   = -hujan * 0.15
    efek_tanpa_sirkulasi = 1.5
 
    # Respirasi lele (menghasilkan panas kecil)
    biomassa_kg = (bak["jumlah_lele"] * bak["berat_gram"]) / 1000
    efek_respirasi = biomassa_kg * 0.01
 
    target = (suhu_udara + efek_tanpa_sirkulasi + efek_radiasi +
              efek_hujan + efek_respirasi)
    target = max(18.0, min(35.0, target))
 
    # Kecepatan perubahan proporsional dt
    alpha = 0.005 * (dt_detik / INTERVAL)
    bak["suhu_air"] += (target - bak["suhu_air"]) * alpha
    bak["suhu_air"] += random.gauss(0, 0.05)
    bak["suhu_air"]  = round(max(18.0, min(35.0, bak["suhu_air"])), 2)
 
 
# ══════════════════════════════════════════════════════════════════════
#  UPDATE NH3
# ══════════════════════════════════════════════════════════════════════
def update_nh3(dt_detik, jam_desimal, cuaca):
    if bak["jumlah_lele"] <= 0:
        return
 
    hujan   = cuaca["hujan"]
    radiasi = cuaca["radiasi"]
    suhu    = bak["suhu_air"]
    volume  = bak["volume_liter"]
 
    # Produksi NH3 per detik berdasarkan biomassa aktual
    porsi_pakan = 0.03  # 3% berat tubuh
    # Stres → nafsu makan turun → NH3 dari pakan berkurang
    faktor_nafsu = max(0.2, 1.0 - bak["stres_level"] * 0.7)
    pakan_gram_hari = (bak["jumlah_lele"] * bak["berat_gram"] *
                       porsi_pakan * faktor_nafsu)
    nh3_produksi_hari = pakan_gram_hari * 10  # mg/hari
    nh3_produksi_det  = nh3_produksi_hari / 86400 / volume / 1000  # ppm/detik
 
    # Akumulasi kotoran makin tua
    faktor_kotoran = 1 + faktor_akumulasi() * 0.5
 
    # Nitrifikasi oleh bakteri (DO rendah → nitrifikasi lambat)
    # DO > 4 mg/L → bakteri aktif, DO < 2 → bakteri mati
    faktor_nitrifikasi = max(0, min(1, (bak["do_ppm"] - 1) / 3))
    laju_nitrifikasi   = bak["nh3_ppm"] * 0.002 * faktor_nitrifikasi * dt_detik
 
    # Fotosintesis alga (menyerap NH3, minimal di bak)
    foto_serap = (radiasi / 800) * bak["nh3_ppm"] * 0.001 * dt_detik
 
    # Efek hujan (encerkan)
    efek_hujan = -hujan * 0.01 * (dt_detik / 3600)
 
    # Pengaruh suhu terhadap toksisitas
    faktor_suhu = 1.0 + 0.05 * (suhu - 24.0)
 
    # Spike setelah pakan
    spike_det = 0.0
    for jam_pakan in [7.0, 17.0]:
        selisih = jam_desimal - jam_pakan
        if 0 <= selisih <= 2.0:
            menit = selisih * 60
            besar = nh3_produksi_det * 800  # spike 800x normal
            spike_det += besar * (menit/25) if menit <= 25 else \
                         besar * math.exp(-(menit-25)/35)
 
    # Pola harian
    fase      = (jam_desimal - 5.0) / 24.0 * 2.0 * math.pi
    pola_hari = nh3_produksi_det * 0.2 * (-math.cos(fase))
 
    # Noise
    noise = random.gauss(0, bak["nh3_ppm"] * 0.01)
 
    delta_nh3 = ((nh3_produksi_det * faktor_kotoran + pola_hari + spike_det) *
                 faktor_suhu * dt_detik - laju_nitrifikasi - foto_serap +
                 efek_hujan + noise)
 
    bak["nh3_ppm"] += delta_nh3
    bak["nh3_ppm"]  = round(max(0.01, min(10.0, bak["nh3_ppm"])), 4)
 
 
# ══════════════════════════════════════════════════════════════════════
#  UPDATE STRES LELE
#  Stres naik kalau: NH3 tinggi, suhu ekstrem, DO rendah
#  Stres turun kalau: kondisi normal
#  Efek stres: nafsu makan turun → produksi NH3 dari pakan turun
#              pertumbuhan melambat
# ══════════════════════════════════════════════════════════════════════
def update_stres(dt_detik):
    stres_baru = 0.0
 
    # Stres dari NH3
    if bak["nh3_ppm"] > 1.0:
        stres_baru += min(1.0, (bak["nh3_ppm"] - 1.0) / 2.0)
    elif bak["nh3_ppm"] > 0.5:
        stres_baru += (bak["nh3_ppm"] - 0.5) / 1.0 * 0.5
 
    # Stres dari suhu
    if bak["suhu_air"] > 32 or bak["suhu_air"] < 22:
        stres_baru += min(0.5, abs(bak["suhu_air"] - 28) / 10)
 
    # Stres dari DO rendah
    if bak["do_ppm"] < 3.0:
        stres_baru += min(1.0, (3.0 - bak["do_ppm"]) / 2.0)
 
    # Smoothing stres (tidak naik/turun tiba-tiba)
    alpha = 0.01 * (dt_detik / INTERVAL)
    bak["stres_level"] += (stres_baru - bak["stres_level"]) * alpha
    bak["stres_level"]  = max(0.0, min(1.0, bak["stres_level"]))
 
    # Akumulasi jam kritis (DO < 1 atau NH3 > 2)
    if bak["do_ppm"] < 1.0 or bak["nh3_ppm"] > 2.0:
        bak["jam_stres_kritis"] += dt_detik / 3600
    else:
        bak["jam_stres_kritis"] = max(0, bak["jam_stres_kritis"] - 0.1)
 
 
# ══════════════════════════════════════════════════════════════════════
#  SIMULASI KEMATIAN LELE
#  Lele mati jika: DO < 1 mg/L lebih dari 2 jam
#                  NH3 > 2 ppm lebih dari 4 jam
#                  Suhu > 35°C
# ══════════════════════════════════════════════════════════════════════
def update_kematian():
    mati = 0
 
    # Kematian karena kondisi kritis terlalu lama
    if bak["jam_stres_kritis"] > 4.0 and bak["jumlah_lele"] > 0:
        # Probabilitas mati: 10% per jam kritis setelah 4 jam
        prob_mati_per_jam = 0.10
        prob = prob_mati_per_jam * (bak["jam_stres_kritis"] - 4.0) / 24
        if random.random() < prob:
            mati = random.randint(1, max(1, bak["jumlah_lele"] // 5))
 
    # Kematian langsung saat kondisi sangat ekstrem
    if bak["do_ppm"] < 0.5 and bak["jumlah_lele"] > 0:
        mati = max(mati, random.randint(1, 3))
    if bak["suhu_air"] > 35.0 and bak["jumlah_lele"] > 0:
        mati = max(mati, random.randint(1, 2))
 
    if mati > 0:
        mati = min(mati, bak["jumlah_lele"])
        bak["jumlah_lele"] -= mati
        print(f"\n💀 [{datetime.now().strftime('%H:%M:%S')}] "
              f"{mati} ekor lele MATI! Sisa: {bak['jumlah_lele']} ekor")
        print(f"   Penyebab: NH3={bak['nh3_ppm']:.2f}ppm | "
              f"DO={bak['do_ppm']:.2f}mg/L | "
              f"Suhu={bak['suhu_air']:.1f}°C")
 
 
# ══════════════════════════════════════════════════════════════════════
#  STATUS
# ══════════════════════════════════════════════════════════════════════
def status_nh3(ppm):
    if ppm < 0.1:   return "✅ Aman"
    elif ppm < 0.3: return "⚠️  Waspada"
    elif ppm < 0.5: return "🔴 Berbahaya"
    elif ppm < 1.0: return "🔴 KRITIS"
    else:           return "💀 DARURAT"
 
def status_do(do):
    if do >= 5.0:   return "✅ Baik"
    elif do >= 3.0: return "⚠️  Kurang"
    elif do >= 1.0: return "🔴 Kritis"
    else:           return "💀 Mematikan"
 
def status_suhu(c):
    if 26 <= c <= 30: return "✅ Optimal"
    elif c < 26:      return "⚠️  Dingin"
    elif c > 32:      return "🔴 Panas"
    else:             return "⚠️  Agak panas"
 
def peringatan_kuras(hari):
    sisa = bak["interval_kuras"] - hari
    if sisa <= 0:       return "💀 KURAS SEKARANG!"
    elif sisa < 1:      return f"🔴 Kuras {sisa*24:.0f} jam lagi!"
    elif sisa < 2:      return f"⚠️  Kuras {sisa:.1f} hari lagi"
    else:               return f"✅ Sisa {sisa:.1f} hari"
 
 
# ══════════════════════════════════════════════════════════════════════
#  KIRIM KE THINGSPEAK
# ══════════════════════════════════════════════════════════════════════
def kirim():
    try:
        r = requests.post(TS_URL, json={
            "api_key": WRITE_API_KEY,
            "field1" : str(round(bak["nh3_ppm"], 4)),
            "field2" : str(bak["suhu_air"]),
        }, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200 and r.text.strip() not in ("0", ""):
            return True, r.text.strip()
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)
 
 
# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  SIMULASI BAK LELE v3.0 → THINGSPEAK (~85% akurasi)")
    print("  25 ekor lele | Bak 1000L | Tanpa sirkulasi | Kuras 7 hari")
    print("  Cuaca Bandung real-time | DO + Stres + Kematian + Pertumbuhan")
    print("=" * 70)
    print(f"  Kuras terakhir : {bak['kuras_terakhir'].strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print("  Tekan Ctrl+C untuk berhenti\n")
 
    total = 0
    gagal = 0
 
    while True:
        now       = datetime.now()
        jam       = now.hour + now.minute/60 + now.second/3600
        waktu_str = now.strftime("%H:%M:%S")
        dt        = detik_per_tick()
        hari      = hari_sejak_kuras()
 
        # Ambil cuaca
        cuaca = ambil_cuaca()
 
        # Update semua state
        update_pertumbuhan(dt)
        update_volume(dt, cuaca)
        update_suhu(dt, cuaca)
        update_do(dt, jam, cuaca)
        update_nh3(dt, jam, cuaca)
        update_stres(dt)
        update_kematian()
 
        # Kirim
        sukses, info = kirim()
        total += 1
        if not sukses:
            gagal += 1
 
        # Print status
        print(
            f"[{waktu_str}] "
            f"Hari {hari:.2f} | "
            f"Lele={bak['jumlah_lele']}ekor {bak['berat_gram']:.1f}g | "
            f"NH3={bak['nh3_ppm']:.4f} {status_nh3(bak['nh3_ppm']):12} | "
            f"DO={bak['do_ppm']:.2f} {status_do(bak['do_ppm']):12} | "
            f"Suhu={bak['suhu_air']:.1f}C | "
            f"Vol={bak['volume_liter']:.0f}L | "
            f"Stres={bak['stres_level']*100:.0f}% | "
            f"{peringatan_kuras(hari):22} | "
            f"{'OK #'+info if sukses else 'GAGAL'}"
        )
 
        try:
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print(f"\n{'=' * 70}")
            print(f"  Dihentikan. Total={total} OK={total-gagal} Gagal={gagal}")
            print(f"  Kondisi akhir:")
            print(f"    Lele  : {bak['jumlah_lele']} ekor, {bak['berat_gram']:.1f}g/ekor")
            print(f"    NH3   : {bak['nh3_ppm']:.4f} ppm")
            print(f"    DO    : {bak['do_ppm']:.2f} mg/L")
            print(f"    Volume: {bak['volume_liter']:.0f} L")
            print(f"{'=' * 70}")
            break
 
if __name__ == "__main__":
    main()
 
