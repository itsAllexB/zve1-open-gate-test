"""Write zv_expected.h for zvread.c from the ZV-E1 2.02 files and the port designs (ZV-E1 port of the A7S III kit, 2026-11-24).

  work/venv/Scripts/python.exe -I -B gen_zv.py

helper_s3/gen_s3.py with this build's files, designs and addresses (modding/ZVE1_PORT.md). Everything the helper compares against is
taken here from the extracted 2.02 update and from modding/designs/{ogsq_zv_v2, outsz2560_zv_v1, ogfile2560_hs_s_zv_v2, lcdfill_zv_v2,
dmmwb_zv_v1}.json. zvread_v2 (2026-11-24, after the first camera test): the stored record's target is ogsq_zv_v2's, and the movie raw write
buffer's size word (dmmwb_zv_v1, the memory manager's RAM copy of DmmCfg.bin) is a site, so that a check shows it stock or new.
Also writes zv_expected.json (what the PC checks against) and zv_reference.json (what the PC needs to read a dump). Read-only on the inputs.
"""
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EX = ROOT / "work/extracted/zve1_202/0700_part_image/dev"
DES = ROOT / "modding/designs"
BASE = 0x108000
LABEL = "zvread_v3"
CP_LO, CP_HI = 0xC0000, 0x2700000                     # coprocessor addresses a read may have: its logs (tomco.txt), image and RAM tables
AVCAM_PHYS, AVCAM_RESERVE = 0x401000000, "@0x401000000"   # kemco.txt: memrsv=0x01000000@0x401000000:ex (byte-identical to the A7C II's)
ID_FILES = {"/libmpr.so": "nflasha15/lib/libmpr.so", "/libsencore.so": "nflasha15/lib/libsencore.so", "/libJiritsu.so": "nflasha15/lib/libJiritsu.so"}
# four 4 KB pages of coprocessor CODE that no design touches (the A7S III kit also hashed a constant-data page; code is the safer choice
# on a body nothing has been read from): a low code page, the size-table set-up's page, the sensor object's set-up, the packers' page
ID_PAGES = (0x128000, 0x4AA000, 0x96D000, 0x788000)
# Ported from the A7S III's dump ranges (build/port_addr.py a7s3_501 zve1_202 ...; modding/ZVE1_PORT.md):
DUMP_RANGES = (("shadow", 0x11BD000, 2), ("matrix", 0x10CD000, 3), ("sizetable", 0x1996000, 1), ("records", 0x25D9000, 5),
               ("kprint", 0xE0000, 32), ("bootlog", 0xC0000, 8),
               # saved records 0x168b6e8 / 0x168b720 (A7S III 0x11a3190 / 0x11a31c8), resize work 0x169de80 (0x11b5c40), division block
               # 0x19ad4d8 (0x1400888), module settings 0x19aec20 (0x1401ff8), core log record 0x19adcb8 (0x1401064, likely), write-buffer
               # ring 0x10e16d4 (0x119a208)
               ("context", 0x168B000, 4), ("resizework", 0x169D000, 1), ("resizestate", 0x19AC000, 4), ("wbuf", 0x10E1000, 2),
               # the screen (lcdfill_zv_v2): the VDF fit function and tables 0x1f5c34.. (fit word 0x1f5c88), the frame widgets' rectangle
               # tables 0xe9b3e0 / 0xe9b458, and the rear panel record 0x1a71824 (type byte 0x1a71840)
               ("display", 0x1F5000, 1), ("frametab", 0xE9B000, 1), ("paneltype", 0x1A71000, 1),
               # the memory manager (dmmwb_zv_v1): its page of pointers 0x19cf000 and the unit records around the write buffer's 0x2580144
               ("dmmglobals", 0x19CF000, 1), ("dmmrecs", 0x2580000, 1))
DESIGNS = ("ogsq_zv_v2", "outsz2560_zv_v1", "ogfile2560_hs_s_zv_v2", "lcdfill_zv_v2", "dmmwb_zv_v1")
UNIT, CLIP, DESC, DSIZE = 0x38F848, 0x38D7EC, 0x38F8E8, 0x88           # av-cam.bin tables of this build (build_ogfile.py zve1_202)


def c_bytes(b):
    return "{" + ",".join(str(x) for x in b) + "}"


def main():
    cp = (EX / "nflasha8/cpapp-b.bin").read_bytes()
    av = (EX / "nflasha3/av-cam.bin").read_bytes()
    lm = (EX / "nflasha15/lib/libmpr.so").read_bytes()
    og, oz, fl, lf, dm = (json.loads((DES / f"{n}.json").read_text(encoding="utf8")) for n in DESIGNS)
    assert og["artifact_sha256"] == hashlib.sha256(cp).hexdigest() == lf["artifact_sha256"]
    assert fl["artifact_sha256"] == {"libmpr.so": hashlib.sha256(lm).hexdigest(), "av-cam.bin": hashlib.sha256(av).hexdigest()}
    out, blobs = [], []

    def blob(b):
        blobs.append(f"static const unsigned char B{len(blobs)}[] = {c_bytes(b)};")
        return f"B{len(blobs) - 1}"

    out.append(f'#define ZV_LABEL "{LABEL}"\n#define CP_LO {CP_LO:#x}U\n#define CP_HI {CP_HI:#x}U\n#define AVCAM_PHYS {AVCAM_PHYS:#x}UL\n'
               f'#define AVCAM_RESERVE "{AVCAM_RESERVE}"')
    out.append("struct id_file { const char *name; unsigned char sha256[32]; };\nstruct id_page { unsigned int address; unsigned char sha256[32]; };\n"
               "struct cp_site { const char *name; unsigned int address, length; const unsigned char *stock, *target; int soft; };\n"
               "struct mp_site { unsigned long offset; unsigned int length; const unsigned char *stock, *target; };\n"
               "struct av_guard { const char *name; unsigned long offset; unsigned int length; unsigned char sha256[32]; };\n"
               "struct dump_range { const char *name; unsigned int address, pages; };")
    rows = [f'    {{"{n}", {c_bytes(hashlib.sha256((EX / p).read_bytes()).digest())}}},' for n, p in ID_FILES.items()]
    out.append("static const struct id_file id_files[] = {\n" + "\n".join(rows) + "\n};")
    sites = []
    for p in og["patches"]:
        a, old, new = int(p["addr"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
        assert cp[a - BASE:a - BASE + len(old)] == old and len(old) == len(new)
        name = p["note"].split(" ")[0] if p["kind"] == "S" else ("record_left" if "left" in p["note"] else "record_right")
        sites.append((name, a, old, new, 0))
    sr = og["stored_record"]
    sites.append(("stored_record", int(sr["address"], 16), bytes.fromhex(sr["stock"]), bytes.fromhex(sr["design"]), 1))
    for s in oz["sites"]:                                 # soft: the size table is zero until a movie mode has run
        sites.append(("outsize", int(s["ram_address"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]), 1))
    for k, g in enumerate(oz["guards"]):
        sites.append((f"outsize_guard{k}", int(g["ram_address"], 16), bytes.fromhex(g["bytes"]), None, 1))
    for k, s in enumerate(lf["sites"]):                   # the screen words are in the loaded image: stock from the file, not soft
        a, old = int(s["ram_address"], 16), bytes.fromhex(s["old"])
        assert cp[a - BASE:a - BASE + 4] == old
        sites.append((f"screen{k}", a, old, bytes.fromhex(s["new"]), 0))
    for s in dm["sites"]:                                 # the memory manager's RAM copy is filled from DmmCfg.bin at start-up: not soft
        sites.append(("rawbuf_size", int(s["ram_address"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]), 0))
    pages = {a & ~0xFFF for _, a, o, _, _ in sites for a in (a, a + len(o) - 1) if a < BASE + len(cp)}
    assert not any(p in pages for p in ID_PAGES), "an identity page holds a design site"
    rows = [f"    {{{a:#x}, {c_bytes(hashlib.sha256(cp[a - BASE:a - BASE + 4096]).digest())}}}," for a in ID_PAGES]
    out.append("static const struct id_page id_pages[] = {\n" + "\n".join(rows) + "\n};")
    rows = []
    for name, a, old, new, soft in sites:
        assert CP_LO <= a and a + len(old) <= CP_HI and len(old) <= 3072
        rows.append(f'    {{"{name}", {a:#x}, {len(old)}, {blob(old)}, {blob(new) if new is not None else "0"}, {soft}}},')
    out.append("static const struct cp_site cp_sites[] = {\n" + "\n".join(rows) + "\n};")
    lmr, avr, av_hi = [], [], 0
    for p in fl["patches"]:
        o, old, new = int(p["file_off"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
        src = lm if p["binary"] == "libmpr.so" else av
        assert src[o:o + len(old)] == old
        (lmr if p["binary"] == "libmpr.so" else avr).append(f"    {{{o:#x}UL, {len(old)}, {blob(old)}, {blob(new)}}},")
        if p["binary"] == "av-cam.bin":
            av_hi = max(av_hi, o + len(old))
    out.append("static const struct mp_site lm_sites[] = {\n" + "\n".join(lmr) + "\n};")
    out.append("static const struct mp_site av_sites[] = {\n" + "\n".join(avr) + "\n};")
    guards = (("unit_rows_0_2", UNIT, 0x30), ("clip_rows_2_7", CLIP + 0x20, 0x60), ("descriptors_0_3", DESC, 4 * DSIZE))
    spans = [(int(p["file_off"], 16), len(p["old"]) // 2) for p in fl["patches"] if p["binary"] == "av-cam.bin"]
    rows = []
    for name, o, n in guards:
        assert all(o + n <= so or so + sn <= o for so, sn in spans), name
        rows.append(f'    {{"{name}", {o:#x}UL, {n}, {c_bytes(hashlib.sha256(av[o:o + n]).digest())}}},')
        av_hi = max(av_hi, o + n)
    out.append("static const struct av_guard av_guards[] = {\n" + "\n".join(rows) + "\n};")
    av_lo = min([so for so, _ in spans] + [o for _, o, _ in guards]) & ~0xFFF
    out.append(f"#define AV_LO {av_lo:#x}UL\n#define AV_HI {av_hi:#x}UL")
    rows = [f'    {{"{n}", {a:#x}, {k}}},' for n, a, k in DUMP_RANGES]
    assert all(CP_LO <= a and a + 4096 * k <= CP_HI for _, a, k in DUMP_RANGES)
    out.append("#if DUMP\nstatic const struct dump_range dump_ranges[] = {\n" + "\n".join(rows) + "\n};\n#endif")
    text = ("/* Generated by gen_zv.py from the ZV-E1 2.02 files and the port designs. Do not edit. */\n#ifndef DUMP\n#define DUMP 0\n#endif\n"
            + "\n".join(blobs) + "\n" + "\n".join(out) + "\n")
    (HERE / "zv_expected.h").write_text(text, encoding="utf8", newline="\n")
    facts = {"label": LABEL, "cp_lo": CP_LO, "cp_hi": CP_HI, "avcam_phys": AVCAM_PHYS, "avcam_reserve": AVCAM_RESERVE,
             "id_files": {n: hashlib.sha256((EX / p).read_bytes()).hexdigest() for n, p in ID_FILES.items()},
             "id_pages": {hex(a): hashlib.sha256(cp[a - BASE:a - BASE + 4096]).hexdigest() for a in ID_PAGES},
             "cp_sites": [{"name": n, "address": hex(a), "length": len(o), "soft": s} for n, a, o, _, s in sites],
             "lm_sites": len(lmr), "av_sites": len(avr), "av_guards": [g[0] for g in guards], "dump_ranges": [[n, hex(a), k] for n, a, k in DUMP_RANGES],
             "designs": {d["design"]: hashlib.sha256((DES / (d["design"] + ".json")).read_bytes()).hexdigest() for d in (og, oz, fl, lf, dm)}}
    (HERE / "zv_expected.json").write_text(json.dumps(facts, indent=1) + "\n", encoding="utf8", newline="\n")
    M, CM, IDS, RECS, REC, N = 0x10CDAF0, 0xDCDD00, 0xDCC524, 0x25D9FA4, 0x170, 39
    matrix, k = [], 0
    while struct.unpack_from("<I", cp, M - BASE + 16 * k)[0]:
        matrix.append([struct.unpack_from("<I", cp, M - BASE + 16 * k)[0], cp[M - BASE + 16 * k + 4:M - BASE + 16 * k + 16].hex()])
        k += 1
    emu = json.loads((ROOT / "evidence/zve1/drvparam_stock_zve1_202.json").read_text(encoding="utf8"))["modes"]
    ref = {"about": "ZV-E1 2.02 reference data for reading a zvread dump; from cpapp-b.bin and build/emu_drvparam.py zve1_202", "matrix_address": hex(M),
           "matrix": matrix, "column_map": [list(struct.unpack_from("<2I", cp, CM - BASE + 8 * i)) for i in range(N)],
           "mode_ids": [hex(x) for x in struct.unpack_from("<%dI" % N, cp, IDS - BASE)], "records_address": hex(RECS), "record_size": REC,
           "emulated_stock_records": {m: v["record"] for m, v in emu.items()}, "size_table_address": "0x1996514",
           "stored_record_design": {"mode": "0x8c0", "index": og["mode_index"], "stock": sr["stock"], "design": sr["design"]},
           # the dump decoder's RAM addresses (ported from the A7S III's; modding/ZVE1_PORT.md). "predicted": the A7S III's distance from the
           # division block, not matched in code
           "ram": {"scaler_block": "0x19ad08c", "scaler_block_predicted": True, "scaler_input": "0x19ad0c8", "scaler_input_predicted": True,
                   "resize_work": "0x169de80", "resize_settings": "0x19aec20", "division_units": "0x19ad4d8", "core_log": "0x19adcb8",
                   "fit_word": "0x1f5c88", "fit_table": "0x1f5c74", "frame_tables": ["0xe9b3e0", "0xe9b458"], "panel_type": "0x1a71840"},
           "screen_design": {s["ram_address"]: [s["old"], s["new"]] for s in lf["sites"]},
           "raw_write_buffer": {"size_word": dm["sites"][0]["ram_address"], "stock": dm["summary"]["stock_unit_size"], "design": dm["summary"]["unit_size"],
                                "full_height_stage_needs": 4288 * 2848}}
    assert len(matrix) == 499 and len(ref["emulated_stock_records"]) == N
    (HERE / "zv_reference.json").write_text(json.dumps(ref) + "\n", encoding="utf8", newline="\n")
    print(f"zv_expected.h: {len(sites)} coprocessor sites, {len(lmr)} libmpr sites, {len(avr)} av-cam sites, {len(text)} bytes of header")


if __name__ == "__main__":
    main()
