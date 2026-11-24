# Port notes: A7S III 5.01 kit → ZV-E1 2.02

Everything here was read from the ZV-E1 2.02 firmware update. The firmware decrypts with the public key the A7 IV, A7C II and A1 II use: 1,446 files, and all 93 checksums are valid. Each step of the kit was emulated: Unicorn ran the ZV-E1's own code where it mattered, and the built helper libraries against a model camera. **The first version ran once on a ZV-E1 (2026-11-23) and restarted the camera when movie mode started. This version fixes that; it has not run yet.**

## The first test, and what it showed (2026-11-23)

The tester ran the five-step apply on macOS. Every site was written and read back, and the closing dump (taken in stills mode) read TARGET everywhere. On the switch to movie mode the camera restarted, and the patch was gone.

**The coprocessor's account.** Its kprint log at 0xE0000 survives a restart without power loss, and the dump taken after the restart holds it:

```text
Snapshot Debug Image Saved
pc: 0x004b2d86  lr: 0x004b2d79  r0: 0x00000000
Running Task: CAM_VD_SEQUENCE (tid:0x000000a0), cpu 3
cause: 4(data abort)  translation fault, page (DFSR: 0x00000807, DFAR: 0x00000000)
```

`0x4b2d86` is `str r0, [r0]` with r0 = 0, a deliberate stop. A counter at 0x19acf78 reached 11, and the routine first logs "FW: S-Ele Refresh ng force exception". This is the A7 IV's signature for the same failure (its F525/F667): the Dev stage was still waiting at its sync point frame after frame, because the first stage never started.

The "time 493, drive mode 0x8c0" record the tester quoted is from the boot after the restart: the camera came back in movie mode, stock.

**The cause: the raw write buffer.** In movie mode the camera core writes each raw frame into one unit of memory id 0x43e (the dump's movie size table names it for 3840 × 2160). Its port set-up (0x2613a8) refuses a frame larger than the unit: it logs `CamCore: AIF%d out[0x%x] > memsize[0x%x]` and reports no error. The required size is ((step + 1) × (rows − 1) + 1) × pitch.

| | ZV-E1 2.02 | A7S III 5.01 |
|---|---|---|
| unit of key 0x57f (id 0x43e) | **10,325,504 = 4288 × 2408**: the stock 4K first stage (2392 + 16 rows) | 26,214,400 |
| its layout | alone in group 0x89 of a 28,311,552-byte parent (key 0x38), limit 7 | alone in group 0x87 of the same parent, limit 6 |
| full-height first stage | 4288 × 2848 = 12,212,224: does not fit | fits |

So the full-height stage never started on the ZV-E1. On the A7S III, the same design works because that unit is 2.5 times larger. Every other memory-manager unit tied to the stage height is the same on both bodies.

**The fix, step L13 (`dmmwb_zv_v1`).**

- **What it writes:** one word of the memory manager's RAM copy of `/cp/DmmCfg.bin`, the size of that unit record at 0x2580150. It goes from 10,325,504 to the A7S III's 26,214,400.
- **Checked in the ZV-E1's own allocator code** (the A7C II's DMM module at −0x1f738, run in Unicorn; `build/build_dmm_zv.py`):
  - seven opens return the new size at the same addresses as stock, and an eighth is refused, as on stock;
  - the parent's other users (ids 0x4b7, 0x4b8) still open;
  - everything frees.
- **Its code is the A7 IV helper's level 13** (`dmmwb4688_v1`, which works on the A7 IV), with this body's addresses: pointers page 0x19cf000, workspace +0x8f0, unit objects +0x444. It writes nothing:
  - if a unit of key 0x57f is in a division still in force (movie mode entered since power-on);
  - if the record or its parent's records are not as in the file;
  - if the workspace pointers are not as expected.

**Also fixed, step L5 (`ogsq_zv_v2`).** v1 left two bytes of the stored record at their stock values: +0x129 and +0x15e, the A7S III's run-time bytes moved by 4 (a guess). On this body they are calculator output. So v1's record held +0x128 = 0x47b1: half stock (0x47ea), half calculated (0x45b1). It also held +0x15e = 47 where the calculator gives 49. The three dumps show the camera's real run-time bytes: +0x11a/+0x11b (0x80, 0x80), which no design changes. v2 writes the whole calculated record, 70 bytes. Whether the two stale bytes alone would have mattered is not known; the buffer stops the camera before they would be used.

**Ruled out.** The read-out table's frame-length fields, which the A7S III design changes: on the ZV-E1 the table has none, and the record field is 0 for every mode. The class table is the same on both bodies. The geometry row's extra field (+8, 418) stays open; it differs between 0x8c0 and 0x28c0, so it may be timing-related.

## What the ZV-E1 shares with the A7S III, and with the A7C II

- **Sensor: the A7S III's.** IMX510, the same drive modes in the same order, minus 0x8010 (39 modes instead of 40).
  - 0x8c0 (FF 4K 23.98p) is still mode 12. 0xe011, the full-height mode the patch borrows, moves from 37 to 36.
  - The same register-matrix column numbers: 0x8c0 uses column 11 and 0xe011 column 1.
  - The window, aux-stream, LC, crop and 0xdcd8a4 rows of both modes are byte-identical to the A7S III's.
- **Platform: the A7C II's.**
  - `kemco.txt` and `usbg_sen.ko` are byte-identical to the A7C II's: av-cam.bin at physical 0x401000000.
  - The stored drive-parameter record is 0x170 bytes.
  - The drive-parameter pointer is at control +0x684.
  - The parameter object is at +0x4ec, with the configuration at +0x54c.
- **USB service route.** `libsencore.so` holds the A7 IV/A7S III login keys (at 0x59a50, 0x59c50, 0x59e50) and the same file commands. `DeviceInfo.xml` is byte-identical to the A7 IV's, the A7S III's and the A7C II's. So the known-answer read cannot tell the bodies apart; the helper itself checks which camera it is on (identity hashes of three libraries and four code pages).

## Sensor side: `ogsq_zv_v2` (the A7S III's `ogsq_s3_v5`; v1 differs only in two stored-record bytes)

| Item | A7S III 5.01 | ZV-E1 2.02 |
|---|---|---|
| mode ids | 0xc70624 (40) | 0xdcc524 (39) |
| column map | 0xc703cc | 0xdcdd00 (second value 3 instead of 4 for every mode) |
| register matrix | 0xf2eb78, 489 rows | 0x10cdaf0, 499 rows |
| receiver type tables | 0xc70e44, 0xc717a4 | 0xdccd10, 0xdcd634 |
| timing, 59.94 / 50 system | 0xc71024 / +0x3c0 | 0xdccee4 / +0x3a8 |
| windows: stream 0 / stream 1 / LC | 0xd67c00 / 0xd681f0 / 0xd687e0 | 0xeb6292 / 0xeb685c / 0xeb6e26 |
| read-out table | 0xd68a10, 18-byte rows | 0xeb7048, **16-byte rows** |
| crop / class | 0xc706c4 / 0xc709e4 | 0xdcc5c0 / 0xdcc8cc |
| geometry row of 0x8c0 | 0xc1801c | 0xd7c034 |
| stored records in RAM | 0x1fe0504, 0x15c each | 0x25d9fa4, 0x170 each |
| sensor object | 0x12a41f0 | 0x17f1f64 |
| record selector | 0x256128 | 0x26f894 |
| 0x8c0/0x820 picture pair | 0xbcfff8 / 0xbd0bb0 | 0xd35f14 / 0xd36acc |

Found through the code that builds each address: `build/port_addr.py` (new) and the map's matching tools. The selector was emulated: 0x8c0 and 0x820 share one pair, as on the A7S III.

**Differences in the stock values the design changes:**

- **Receiver type.** The 4K rows hold 6, 3 (A7S III 5, 3); every 10-bit mode on the ZV-E1 holds 6. The design writes 0, 2 (0xe011's), as on the A7S III.
- **24p timing row.** 287 × 5220, P 87, E 56 (A7S III 266 × 5628, P 67, E 53). The frame length is the same: 1,501,500 units = 23.976 fps. The design writes the A7S III's working row, 313 × 4788, P 57, E 34 (E < P). The 50 Hz row is identical on both bodies.
- **Read-out table.** No frame-length fields (they are 0 in every row). Only the row fields 618 → 728 change.
- **Geometry row.** It has one more field, +8, which holds 418 for 0x8c0 and 0 on the A7S III. It is left alone. **Not known what it is.**

**Picture records.** The ZV-E1's stock 4K pair differs from the A7S III's in about 50 words: 80 leading columns instead of 20, line-length words like the A7C II's, and a single-row flag that is set. So the records were rebuilt, not copied. The model is `build_og_s3.py`'s: the A7 IV's field classes, frame fields from this body's full-height still pair (0xd4264c / 0xd43204), and this body's own packers (CamArc 0x267f48, CamNrs 0x7885cc, CamSig 0x7904e0, CamLrc 0x788588, Dev 0x787ae8 / 0x78796e, fit 0x790040).

- All 154 model fields fit the ZV-E1's stock records.
- The ZV-E1's packers reproduce every stock packer word.
- The result has the same scaler numbers as the A7S III's working v5: Lrc 2180 × 2848 → 2176 × 2408, final 2144 + 2096 × 2392.
- Then the v5 link-format words for a 12-bit link. The rule holds on all 38 ZV-E1 records.

**Stored record.** The ZV-E1's own calculator (0x390fa0) was run with every cell applied. In v2, 70 bytes differ, and +6/+7 carry the sampling ratio 16/19. v1 left out two bytes (a guess; see above). If the camera holds other values in those bytes, step L5 refuses and writes nothing.

## Output size: `outsz2560_zv_v1`

The size table is filled by 0x4aadd8 into base 0x19964c4 + 0x50, as the A7C II's, including its extra 8K class. The 3840 × 2160 entry at 0x199655c becomes 3840 × 2560. There are two guards.

## Encoder side: `ogfile2560_hs_s_zv_v1`

- libmpr.so `g_videoParamComb` is at the A7 IV's position −0x205c0. av-cam.bin: unit types 0x38f848, descriptors 0x38f8e8, clip table 0x38d7ec (codes 3 / 23, as on the A7S III).
- **The descriptor table has 647 rows of 0x88 bytes** (A7S III: 689 × 0x90).
- The same 29 descriptors are chosen: 101 av-cam + 4 libmpr sites.

## MP4 header height: `ogfile2560_hs_s_zv_v2` (steps M19 / M20)

- v1 plus v1's two `optional_sites`, as the A7 IV's `ogfile2560_hs_s_v2`. The MP4 writer's request set-up at 0x207d14 (the A7 IV's 0x222b18, −0x1ae04) writes width, height and sample entry per case; its jump table is at 0x2ba0e8.
- 0x207d8c (the 3840-wide AVC case, `avc1`) and 0x207dd8 (the 3840-wide HEVC case, `hvc1`): `mov w6,#0x870` → `mov w6,#0xa00`. They are the function's only 3840-wide instructions: of the jump table's 14 cases, 2 and 9 reach the AVC one and 5 and 7 the HEVC one, so every 3840-wide recording that goes through the function gets 2560 while they are applied. Which record settings use cases 9 and 7 is not known.
- Guards as in the A7 IV's v2 library: the two instructions before and the two after each site, which are byte-identical to the A7 IV's.
- `06 0e 81 52` occurs a third time, at 0x207f3c: the 4096-wide case (`mov w7,#0x1000` follows). It is not touched.
- v1's note on the profile-compatibility lookups (0x222714) was not followed further here. On a ZV-E1 (2026-11-24) M19 was applied three times from a battery pull, every step DONE (each M19 result: the six libmpr.so sites "as expected", then "written and read back"). The XAVC HS 4K 24p clips recorded normally: the stream, tkhd, the `hvc1` sample entry and Sony's VPRF say 3840 × 2560; Sony's XML still says `HEVC_3840_2160`. `open_gate_putback` in the same power-on (C20, S17, M20, L17, L6, L14) was DONE throughout; M20 wrote back 107 sites, and the next clip was 3840 × 2160 in stream and headers.
- Both instructions are in libmpr.so's code in the camera's main process (`im.elf`), written through `/proc/self/mem` like the four `g_videoParamComb` rows. After a power switch (a few seconds off, battery in) a `check_readonly` read every coprocessor site as stock (stored record "filled at run time", not counted) and all 101 av-cam.bin sites and the four libmpr.so rows as applied; that v2 check did not read the two header instructions. `im.elf`'s main-thread context-switch counts kept growing across the power switch (17,122 → 17,829) and were back at about 17,122 after a battery pull, which fits the process running on. A 4K 24p clip in that state was a 3840 × 2560 stream with the 16:9 picture in the middle and 200 black rows above and below, and 3840 × 2560 in its headers: the header height matched the stream. The leftover state is the encoder side, which v1 leaves behind as well (with v1 such a file would say 2160 in its headers over a 2560 stream). HD and S&Q clips recorded normally in that state; 4K 59.94p crashed and restarted the camera, after which 4K clips were plain 3840 × 2160. Seen in one session. A plain 3840 × 2160 clip from an earlier session was most likely recorded after a battery pull rather than only the power switch (not logged). A battery pull with M19 applied was checked: afterwards every site read stock and the next 4K clip was plain 3840 × 2160 in stream and headers.
- Built by `modding/zve1/build_ogfile_meta_zv.py` from v1 and `gen_zv_write.py` (which now takes single libmpr.so instructions as sites). The generator gives the v1, lcdcycle and words headers byte for byte as published. M19 / M20 were built with zig 0.17.1 (clang 22.1.8), not the kit's ziglang (clang 18.1.6); the published L19 / L20 and the same source built that way give the same result in emulation.
- Emulated (the library's own code, against libmpr.so and av-cam.bin of 2.02): apply, apply again (NOTHING TO DO), put back byte for byte, partial states as after a power switch (header only, all of libmpr.so, header and av-cam: M19 completes, M20 returns all to stock; L20 leaves the header at 2560), a wrong guard or a site with other bytes (nothing written).

## Screen: `lcdfill_zv_v2` and `lcdcycle_zv_v1`

The rear screen is 3.0-type, 1,036,800 dots = 720 × 480 = **3:2**, and there is **no viewfinder**. So the A7S III's 4:3 step (`lcdratio32_s3_v1`) does not apply. The A7 IV / A7C II step does instead:

- **`lcdfill_zv_v2`:**
  - Fit word 0x1f5c88 goes from 3 to 0. The fit function at 0x1f5c34 and its tables are byte-identical to the A7 IV's.
  - The rear-panel 16:9 entry of the AF-window and tracking-frame tables (0xe9b420, 0xe9b498) goes from (0, 38, 640, 404) to (0, 0, 640, 480).
  - That is 5 words. The A7C II's remote-send frame widget does not exist on this body.
- **`lcdcycle_zv_v1`:** a routine in appFw.so's .rela.dyn page (cave 0x17d6000, 1,460 bytes) and one branch at 0x1f7c61c.
  - **C2** steps 3:2 → 2:1 → 2.25:1 → 2.4:1 → 3:2 in movie mode (event 0x2150003). The ZV-E1 has C1 (Background Defocus) and C2 (Step zoom); C2 was chosen.
  - 66 emulated cases pass.
  - That the physical C2 key sends 0x2150003 is assumed from the event name.

## The kit

- **Helper libraries:** `helper_zv/` holds `zvread.c` (from `s3read.c`, with `zvread_v3` observing both MP4 header sites and distinguishing `VERDICT READY (stock preflight)` from `VERDICT READY (open gate applied)` while rejecting mixed/partial states as `VERDICT NOT READY`, built with `ziglang==0.13.0` / `clang version 18.1.6` via `build_zv.sh`) and the A7 IV helper's write levels with this body's tables: `gen_zv_write.py` (from the A7C II's) and `build_zv_write.sh`.
- **Scripts:** `zv_run.py` and `zv_apply.py` (from `s3_run.py` / `s3_apply.py`). The dump decoder's RAM addresses were ported too. Two are predictions, not matches: the second scaler's block and input words.

**Checked offline:**

- Read-only libraries: 10 cases.
  - Stock reads READY.
  - Applied reads TARGET everywhere.
  - An A7S III image is refused.
  - Without the av-cam reservation, av-cam.bin is not read.
  - With an existing result, the helper does nothing.
- Write libraries: 45 cases. Apply, apply again, put back byte for byte, foreign bytes, a wrong guard, lost writes undone, the C2 hook written last and removed first. L13/L14 on the memory manager's state as the ZV-E1's own DMM code leaves it: the word written, then the same code hands out 26,214,400-byte buffers; refused while a movie buffer is open; refused with a record, a parent record or the workspace pointer not as expected.
- Every launcher: `--selftest` and `--dry-run`.
- The Android app's Python side, on the kit's simulated camera:
  - check;
  - the six-step apply and closing session;
  - put back;
  - a cancelled dialog;
  - Stop waiting.

## Not known until a ZV-E1 runs it

- Whether the full-height first stage runs once the buffer holds it (the A7S III's does, with this buffer size).
- Everything the A7S III kit left open: the live-view fault when movie mode is entered from stills, exposure and autofocus, and 60p.
- Whether receiver type 6 (the ZV-E1's 4K) behaves like the A7S III's 5 when replaced.
- The geometry row's extra field.
- Whether the power switch always leaves the encoder side applied. Seen once: coprocessor sites stock, encoder sites applied, a letterboxed 3840 × 2560 clip; a battery pull clears everything, header included.

Known from the first test: every site holds the stock bytes the files predict; the rear panel's type byte is 3 (3:2); the stored record's run-time bytes are +0x11a/+0x11b; a restart does not keep the patch.
- The physical C2 key's event.
- The live-view and preview behaviour of the AI-unit body.
