from datetime import datetime
import io
from flask import Flask, jsonify, make_response, render_template, request, send_file

app = Flask(__name__)

# ==========================================
# KONFIGURASI IDENTITAS KLINIK & STRUK
# ==========================================
NAMA_KLINIK = "KLINIK CARELINE"
ALAMAT_KLINIK = "Jln. Kemanggisan Pulo, Jakarta Barat"
PESAN_TUNGGU = "Mohon menunggu hingga nomor dipanggil"

HARI_ID = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}

BULAN_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

# ==========================================
# STATE ANTREAN & APLIKASI
# ==========================================
state = {
    "theme": "dark",
    "antrean": {
        "Umum": [],
        "Asuransi": [],
        "BPJS": [],
    },
    "riwayat": [],
    "counter": {
        "Umum": 1,
        "Asuransi": 1,
        "BPJS": 1,
    },
    "aktif": {
        "Umum": "-",
        "Asuransi": "-",
        "BPJS": "-",
    },
    "pulse_target": None,  # format: {"kategori": "Umum", "seq": 1}
    "pulse_seq": 0,
}


def format_tanggal_indonesia(waktu: datetime) -> str:
    nama_hari = HARI_ID.get(waktu.weekday(), "")
    nama_bulan = BULAN_ID.get(waktu.month, "")
    return f"{nama_hari} {waktu.day} {nama_bulan} {waktu.year} {waktu.strftime('%H:%M:%S')}"


def build_payload(kategori_filter="Semua", cari=""):
    cari_clean = (cari or "").strip().lower()
    riwayat_filtered = []
    for item in state["riwayat"]:
        cocok_kat = (kategori_filter == "Semua") or (item["kategori"] == kategori_filter)
        cocok_cari = (not cari_clean) or (cari_clean in item["nomor"].lower())
        if cocok_kat and cocok_cari:
            riwayat_filtered.append(item)

    now = datetime.now()
    return {
        "theme": state["theme"],
        "jam": now.strftime("%H:%M:%S"),
        "tanggal": now.strftime("%d-%m-%Y"),
        "stats": {
            "Umum": len(state["antrean"]["Umum"]),
            "Asuransi": len(state["antrean"]["Asuransi"]),
            "BPJS": len(state["antrean"]["BPJS"]),
            "dilayani": len(state["riwayat"]),
        },
        "aktif": state["aktif"],
        "antrean": state["antrean"],
        "riwayat": riwayat_filtered,
        "pulse": state["pulse_target"],
        "klinik": {
            "nama": NAMA_KLINIK,
            "alamat": ALAMAT_KLINIK,
            "pesan": PESAN_TUNGGU,
        },
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def get_state():
    kat = request.args.get("kategori", "Semua")
    cari = request.args.get("cari", "")
    return jsonify(build_payload(kat, cari))


@app.route("/api/theme", methods=["POST"])
def toggle_theme():
    state["theme"] = "light" if state["theme"] == "dark" else "dark"
    return jsonify(build_payload())


@app.route("/api/ambil", methods=["POST"])
def ambil_antrean():
    data = request.get_json(silent=True) or {}
    kategori = data.get("kategori")
    if kategori not in ("Umum", "Asuransi", "BPJS"):
        return jsonify({"error": "Kategori tidak valid"}), 400

    prefix_map = {"Umum": "U", "Asuransi": "A", "BPJS": "B"}
    nomor_urut = state["counter"][kategori]
    nomor = f"{prefix_map[kategori]}{nomor_urut:03d}"
    state["counter"][kategori] += 1

    state["antrean"][kategori].append({"nomor": nomor, "kategori": kategori})

    waktu_cetak = datetime.now()
    struk = {
        "nomor": nomor,
        "kategori": kategori,
        "waktu_indo": format_tanggal_indonesia(waktu_cetak),
        "klinik": NAMA_KLINIK,
        "alamat": ALAMAT_KLINIK,
        "pesan": PESAN_TUNGGU,
    }

    payload = build_payload()
    payload["struk"] = struk
    return jsonify(payload)


@app.route("/api/panggil", methods=["POST"])
def panggil_antrean():
    data = request.get_json(silent=True) or {}
    kategori = data.get("kategori")
    if kategori not in ("Umum", "Asuransi", "BPJS"):
        return jsonify({"error": "Kategori tidak valid"}), 400

    antrean_kat = state["antrean"][kategori]
    if not antrean_kat:
        return jsonify({"message": f"Tidak ada antrean menunggu untuk kategori {kategori}."}), 200

    pasien = antrean_kat.pop(0)
    nomor_dipanggil = pasien["nomor"]
    state["aktif"][kategori] = nomor_dipanggil

    state["pulse_seq"] += 1
    state["pulse_target"] = {"kategori": kategori, "seq": state["pulse_seq"]}

    state["riwayat"].insert(
        0,
        {
            "nomor": nomor_dipanggil,
            "kategori": kategori,
            "waktu": datetime.now().strftime("%H:%M:%S"),
        },
    )

    payload = build_payload()
    payload["message"] = f"Memanggil nomor {nomor_dipanggil} ({kategori})"
    return jsonify(payload)


@app.route("/api/panggil-ulang", methods=["POST"])
def panggil_ulang():
    data = request.get_json(silent=True) or {}
    kategori = data.get("kategori")
    if kategori not in ("Umum", "Asuransi", "BPJS"):
        return jsonify({"error": "Kategori tidak valid"}), 400

    if state["aktif"][kategori] == "-":
        return jsonify({"message": f"Belum ada nomor aktif untuk kategori {kategori}."}), 200

    state["pulse_seq"] += 1
    state["pulse_target"] = {"kategori": kategori, "seq": state["pulse_seq"]}
    payload = build_payload()
    payload["message"] = f"Panggil ulang nomor {state['aktif'][kategori]} ({kategori})"
    return jsonify(payload)


@app.route("/api/reset", methods=["POST"])
def reset_semua():
    state["antrean"] = {"Umum": [], "Asuransi": [], "BPJS": []}
    state["riwayat"] = []
    state["counter"] = {"Umum": 1, "Asuransi": 1, "BPJS": 1}
    state["aktif"] = {"Umum": "-", "Asuransi": "-", "BPJS": "-"}
    state["pulse_target"] = None
    payload = build_payload()
    payload["message"] = "Semua antrean berhasil direset."
    return jsonify(payload)


@app.route("/api/ekspor")
def ekspor_laporan():
    if not state["riwayat"]:
        return make_response("Belum ada data riwayat untuk diekspor.", 400)

    total_umum = sum(1 for r in state["riwayat"] if r["kategori"] == "Umum")
    total_asuransi = sum(1 for r in state["riwayat"] if r["kategori"] == "Asuransi")
    total_bpjs = sum(1 for r in state["riwayat"] if r["kategori"] == "BPJS")
    tgl = datetime.now().strftime("%d-%m-%Y")

    lines = [
        "=" * 60,
        "        LAPORAN RESMI ANTREAN KLINIK",
        f"        Tanggal: {tgl}",
        "=" * 60,
        "",
        f"Total Pasien Dilayani : {len(state['riwayat'])}",
        f"- Umum     : {total_umum}",
        f"- Asuransi : {total_asuransi}",
        f"- BPJS     : {total_bpjs}",
        "-" * 60,
        "DAFTAR NOMOR TERPANGGIL:",
    ]
    for idx, r in enumerate(state["riwayat"], 1):
        lines.append(f"{idx}. [{r['nomor']}] | Kat: {r['kategori']} | Jam: {r['waktu']}")
    lines.append("=" * 60)

    konten = "\n".join(lines) + "\n"
    buf = io.BytesIO(konten.encode("utf-8"))
    nama_file = f"Laporan_Klinik_CareLine_{datetime.now().strftime('%Y-%m-%d')}.txt"
    return send_file(buf, as_attachment=True, download_name=nama_file, mimetype="text/plain; charset=utf-8")


@app.route("/api/impor", methods=["POST"])
def impor_laporan():
    if "file" not in request.files:
        return jsonify({"error": "File tidak ditemukan"}), 400

    file = request.files["file"]
    konten = file.read().decode("utf-8", errors="ignore")
    count = 0

    for line in konten.splitlines():
        if "[" in line and "]" in line and "Kat:" in line:
            try:
                part_no = line.split("[")[1].split("]")[0].strip()
                kat_part = line.split("Kat:")[1].split("|")[0].strip()
                jam_part = line.split("Jam:")[-1].strip()
                if kat_part in ("Umum", "Asuransi", "BPJS"):
                    state["riwayat"].append(
                        {"nomor": part_no, "kategori": kat_part, "waktu": jam_part}
                    )
                    count += 1
            except Exception:
                pass

    payload = build_payload()
    payload["message"] = f"Berhasil mengimpor {count} data riwayat dari file!"
    return jsonify(payload)


@app.route("/struk")
def halaman_struk():
    nomor = request.args.get("nomor", "U001")
    kategori = request.args.get("kategori", "Umum")
    waktu_indo = request.args.get("waktu", format_tanggal_indonesia(datetime.now()))
    return render_template(
        "struk.html",
        nama_klinik=NAMA_KLINIK,
        alamat_klinik=ALAMAT_KLINIK,
        pesan_tunggu=PESAN_TUNGGU,
        nomor=nomor,
        kategori=kategori,
        waktu_indo=waktu_indo,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)