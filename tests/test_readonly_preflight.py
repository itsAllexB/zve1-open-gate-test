"""Offline regression tests. Run with python -m unittest discover -s tests -v."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CT6 = ROOT / "windows/tools/camera_tests/CT6_memory_read_check"
sys.path.insert(0, str(CT6))
import zv_apply
import zv_run

HEADERS = ("0x207d8c", "0x207dd8")
DESIGN = ROOT / "windows/tools/modding/designs/ogfile2560_hs_s_zv_v2.json"
SITES = json.loads(DESIGN.read_text())["patches"]


def report(mode="check", applied=(), cp_states=None, verdict="VERDICT READY (stock preflight)"):
    """Synthetic captured rows. Leave the helper verdict optimistic for negative tests."""
    spec = zv_run.expected()
    cp_states = cp_states or {}
    rows = [f"zvread zvread_v3 {mode} for ZV-E1 2.02; read-only"]
    for name, digest in spec["id_files"].items():
        rows.extend([f"file {name} path {name} mapped 0x1000",
                     f"  bytes 4096 sha256 {digest}  SAME as the 2.02 update"])
    for addr, digest in spec["id_pages"].items():
        rows.append(f"page {addr} sha256 {digest}  SAME as the 2.02 update")
    for site in spec["cp_sites"]:
        state = cp_states.get(site["name"], "STOCK")
        rows.append(f"site {site['name']} {site['address']} len {site['length']}  {state}")
    for site in SITES:
        addr = site["file_off"]
        prefix = f"lm {addr} at 0x1000" if site["binary"] == "libmpr.so" else f"av {addr}"
        value, state = (site["new"], "TARGET") if addr in applied else (site["old"], "STOCK")
        rows.append(f"{prefix} bytes {value}  {state}")
    for guard in spec["av_guards"]:
        rows.append(f"guard {guard} 0x1000 len 16  SAME")
    return rows + [verdict, "== done"]


def applied_report(mode="dump", *, meta=True, screen="fill", stored_record="TARGET",
                   verdict="VERDICT READY (open gate applied)"):
    """Synthetic coherent post-apply movie_session() dump or check."""
    spec = zv_run.expected()
    cp_states = {}
    for site in spec["cp_sites"]:
        name = site["name"]
        if not site["soft"] and not name.startswith("screen"):
            cp_states[name] = "TARGET"
        elif name == "screen0":
            cp_states[name] = "TARGET" if screen == "fill" else "STOCK"
        elif name.startswith("screen"):
            cp_states[name] = "STOCK" if screen == "none" else "TARGET"
        elif name == "stored_record":
            cp_states[name] = stored_record
        elif name == "outsize":
            cp_states[name] = "TARGET"
        else:
            cp_states[name] = "STOCK"
    mp_applied = {s["file_off"] for s in SITES if meta or s["file_off"] not in HEADERS}
    return report(mode=mode, applied=mp_applied, cp_states=cp_states, verdict=verdict)


def result(rows, mode="check"):
    with patch.object(zv_run, "WHICH", mode):
        return zv_run.check_result(("\n".join(rows) + "\n").encode())["s3"]


class ReadOnlyPreflight(unittest.TestCase):
    def blocked(self, rows, mode="check"):
        facts = result(rows, mode=mode)
        self.assertIs(facts["ready"], False)
        self.assertEqual(facts["state"], "not_ready")
        self.assertEqual(facts["verdict"], "VERDICT NOT READY")
        return facts

    def test_native_verdict_and_header_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "preflight"
            subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(CT6 / "helper_zv"),
                            str(ROOT / "tests/preflight_counts.c"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_complete_stock_check_and_dump(self):
        for mode in ("check", "dump"):
            with self.subTest(mode=mode):
                facts = result(report(mode), mode)
                self.assertIs(facts["ready"], True)
                self.assertEqual(facts["state"], "stock")
                self.assertEqual(facts["verdict"], "VERDICT READY (stock preflight)")

    def test_post_apply_movie_session_dump_and_gate(self):
        cases = [
            ("full_v2", dict(meta=True, screen="fill", stored_record="TARGET")),
            ("no_meta", dict(meta=False, screen="fill", stored_record="TARGET")),
            ("no_screen", dict(meta=True, screen="none", stored_record="TARGET")),
            ("c2_cycled", dict(meta=True, screen="c2", stored_record="TARGET")),
            ("runtime_stored_record", dict(meta=True, screen="fill", stored_record="OTHER (not counted: filled at run time)")),
        ]
        for label, kw in cases:
            with self.subTest(case=label):
                facts = result(applied_report("dump", **kw), mode="dump")
                self.assertIs(facts["ready"], True)
                self.assertEqual(facts["state"], "applied")
                self.assertEqual(facts["verdict"], "VERDICT READY (open gate applied)")
                manifest = {"results": {"which": "dump", "ct6": {"result": {"s3": facts}}}}
                with patch.object(zv_apply, "sessions", return_value=[(Path("CT6_offline"), manifest)]):
                    self.assertEqual(zv_apply.last_check(), ("CT6_offline", True))

    def test_warm_power_switch_mixed_state_blocked(self):
        all_mp = {row["file_off"] for row in SITES}
        no_hdr_mp = all_mp - set(HEADERS)
        for mp_applied in (all_mp, no_hdr_mp):
            for sr in ("STOCK", "OTHER (not counted: filled at run time)"):
                for verdict in ("VERDICT READY (stock preflight)", "VERDICT READY (open gate applied)"):
                    rows = report(applied=mp_applied, cp_states={"stored_record": sr}, verdict=verdict)
                    facts = self.blocked(rows)
                    manifest = {"results": {"which": "check", "ct6": {"result": {"s3": facts}}}}
                    with patch.object(zv_apply, "sessions", return_value=[(Path("CT6_offline"), manifest)]):
                        self.assertEqual(zv_apply.last_check(), ("CT6_offline", False))

    def test_either_or_both_headers_on_stock_sensor_blocked(self):
        for applied in ((HEADERS[0],), (HEADERS[1],), HEADERS):
            for verdict in ("VERDICT READY (stock preflight)", "VERDICT READY (open gate applied)"):
                with self.subTest(applied=applied, verdict=verdict):
                    self.blocked(report(applied=applied, verdict=verdict))

    def test_partial_cp_og_and_screen_on_stock_blocked(self):
        self.blocked(report(cp_states={"screen0": "TARGET", "screen1": "TARGET",
                                       "screen2": "TARGET", "screen3": "TARGET", "screen4": "TARGET"}))
        self.blocked(report(cp_states={"rawbuf_size": "TARGET"}))
        self.blocked(report(cp_states={"C": "TARGET"}))

        # Invalid partial applied states (even with forged applied verdict)
        bad_applied = applied_report("dump")
        for needle, repl in [
            ("site rawbuf_size 0x2580150 len 4  TARGET", "site rawbuf_size 0x2580150 len 4  STOCK"),
            ("site stored_record 0x25db0e4 len 368  TARGET", "site stored_record 0x25db0e4 len 368  STOCK"),
            ("site outsize 0x199655c len 4  TARGET", "site outsize 0x199655c len 4  STOCK"),
            ("site outsize 0x199655c len 4  TARGET", "site outsize 0x199655c len 4  OTHER (not counted: filled at run time)"),
            ("site outsize_guard0 0x1996554 len 8  STOCK", "site outsize_guard0 0x1996554 len 8  OTHER (not counted: filled at run time)"),
            ("site screen1 0xe9b420 len 4  TARGET", "site screen1 0xe9b420 len 4  STOCK"),
            ("lm 0x207d8c at 0x1000 bytes 06408152  TARGET", "lm 0x207d8c at 0x1000 bytes 060e8152  STOCK"),
        ]:
            idx = bad_applied.index(needle)
            self.blocked([*bad_applied[:idx], repl, *bad_applied[idx + 1:]], mode="dump")

        # screen0 TARGET with frame tables STOCK -> blocked
        bad_screen0 = applied_report("dump", screen="none")
        idx = bad_screen0.index("site screen0 0x1f5c88 len 4  STOCK")
        self.blocked([*bad_screen0[:idx], "site screen0 0x1f5c88 len 4  TARGET", *bad_screen0[idx + 1:]], mode="dump")

    def test_header_missing_unmapped_unknown_mislabeled_or_duplicated(self):
        for addr in HEADERS:
            rows = report()
            idx = next(i for i, line in enumerate(rows) if line.startswith(f"lm {addr} "))
            other = next(line for line in rows if line.startswith("lm ") and addr not in line)
            for replacements in ([], [f"lm {addr}  NOT MAPPED"], [f"lm {addr} at 0x1000 bytes ffffffff  OTHER"],
                                 [f"lm {addr} at 0x1000 bytes ffffffff  STOCK"],
                                 [f"lm {addr} at 0x1000 bytes ffffffff  TARGET"], [other], [rows[idx]] * 2):
                with self.subTest(addr=addr, replacements=replacements):
                    self.blocked(rows[:idx] + replacements + rows[idx + 1:])

        # Duplicate cp_site line
        rows = report()
        idx = next(i for i, line in enumerate(rows) if line.startswith("site C "))
        self.blocked(rows[:idx] + [rows[idx], rows[idx]] + rows[idx + 1:])

    def test_missing_identity_guard_problem_completion_or_current_header(self):
        rows = report()
        for prefix in ("page ", "guard ", "== done", "site ", "av "):
            idx = next(i for i, line in enumerate(rows) if line.startswith(prefix))
            with self.subTest(prefix=prefix):
                self.blocked(rows[:idx] + rows[idx + 1:])
        self.blocked([rows[0].replace("v3", "v2"), *rows[1:]])
        self.blocked([*rows[:-2], "VERDICT NOT READY", *rows[-2:]])
        self.blocked([rows[0], "!! read failed -21", *rows[1:]])

    def test_runtime_filled_sensor_exception(self):
        rows = report()
        soft = next(row for row in zv_run.expected()["cp_sites"] if row["soft"])
        idx = next(i for i, line in enumerate(rows) if line.startswith(f"site {soft['name']} {soft['address']} "))
        for state, ready in (("OTHER (not counted: filled at run time)", True), ("NOT READ", False), ("TARGET", False)):
            candidate = rows.copy()
            candidate[idx] = candidate[idx].replace("STOCK", state)
            self.assertIs(result(candidate)["ready"], ready)

    def test_saved_result_gate(self):
        for mode in ("check", "dump"):
            stock = result(report(mode), mode)
            applied = result(applied_report(mode), mode)
            mixed = result(report(mode, applied=HEADERS), mode)
            old = dict(stock, header=stock["header"].replace("v3", "v2"))
            for facts, ready in ((stock, True), (applied, True), (mixed, False), (old, False)):
                manifest = {"results": {"which": mode, "ct6": {"result": {"s3": facts}}}}
                with patch.object(zv_apply, "sessions", return_value=[(Path("CT6_offline"), manifest)]):
                    self.assertEqual(zv_apply.last_check(), ("CT6_offline", ready))
