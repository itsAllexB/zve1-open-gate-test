# ZV-E1 open gate: test kit (firmware 2.02)

<p><b>Second version, run on one ZV-E1 (firmware 2.02, 2026-11-24): it records 3840 × 2560 at 24p in XAVC HS 4K.</b> See <a href="#tested-on-a-zv-e1">Tested on a ZV-E1</a> for what worked and what did not. This is the A7S III open-gate kit, which works on an A7S III, rebuilt for the ZV-E1 from the ZV-E1's own firmware. The first version was run once (2026-11-23): every step applied, then the camera restarted itself when movie mode started. The cause has been found and fixed (see <a href="#what-changed-after-the-first-test">What changed after the first test</a>). Everything the kit writes goes to RAM only, and a battery pull removes it.</p>

The kit records a true 3840 × 2560 (3:2) file of the whole sensor area in XAVC HS 4K and XAVC S 4K at 23.98p. It also shows the live view at 3:2 on the rear screen and adds an anamorphic preview on the C2 key.

**MP4 headers (since 2026-11-24): no remux needed.** The encoder step now also sets the height in the MP4 headers (tkhd, the stsd entry and Sony's PROF box) to 2560, as `ogfile2560_hs_s_v2` does on the A7 IV, so the file says 3840 × 2560 as it comes off the card and editors show it at 3:2. Sony's own XML (the `M01.XML` file next to the clip, and the XML inside the clip) still says 3840 × 2160, 16:9 (`HEVC_3840_2160`); Catalyst Browse and Gyroflow read that. `--no-meta` gives the earlier encoder step, with 3840 × 2160 in the headers.

**The power switch is not a full reset on this body.** After switching off for a few seconds and on again (battery in), `check_readonly` read every coprocessor site as stock (sensor, output size, screen, raw write buffer) but the encoder side as still applied (all 101 av-cam.bin sites and the four libmpr.so rows; the v2 check used in that session did not read the two header instructions). A 4K 24p clip recorded in that state was a 3840 × 2560 file with the 16:9 picture in the middle and exactly 200 black rows above and below; its headers said 3840 × 2560, which matches the stream. That is one clip, so take it as what was seen, not as a rule. `open_gate_putback` (in the same power-on) or a battery pull clears the encoder side; see below.

The desktop read-only check and dump now include both MP4 header sites (AVC and HEVC). A fresh preflight reports `VERDICT READY (stock preflight)` only when the firmware identity matches and all required sites are stock (with the existing runtime-filled exception for `stored_record`, `outsize`, and `outsize_guard0`/`outsize_guard1`). A coherent open-gate `movie_session()` dump (default `apply`, `--no-meta`, `--no-screen`, or C2-cycled anamorphic preview, with `stored_record` target or runtime-filled) reports `VERDICT READY (open gate applied)`. Mixed or partial states—including a warm power-switch state, either MP4 header by itself, partial `cp_og` sites, or screen-on-stock—report `VERDICT NOT READY`. The desktop launcher requires a new v3 result because v2 did not observe either header. The offline regression suite runs from the repository root with `python -m unittest discover -s tests -v` and a host C compiler. The two bundled v3 read-only libraries were built with `ziglang==0.13.0` (`clang version 18.1.6`) using `helper_zv/build_zv.sh` and have been checked offline.

**Why it should carry over:** the ZV-E1 has the A7S III's sensor (IMX510) and the same list of sensor modes, less one. The 4K mode and the full-height mode the patch borrows have the same table values as on the A7S III, except for a few documented differences (see `PORT_NOTES.md`). The picture records were rebuilt with the same model, and the scaler numbers come out the same as the A7S III's working version. The USB service route uses the same commands and login.

**What is different from the A7S III kit:**

- **The screen.** The ZV-E1 has a 3:2 rear screen and no viewfinder; the A7S III has 4:3 panels. So the screen step is the A7 IV's: the whole 3:2 picture fills the screen, with the focus frames.
- **The key.** The preview cycle is on **C2**: 3:2 → 2:1 (1.33x) → 2.25:1 (1.5x) → 2.4:1 (1.6x) → 3:2. While it is applied, C2's own function (Step zoom by default) is gone in movie mode.
- **Switching modes.** The ZV-E1 has no mode dial. Where the A7S III instructions say "dial on stills / movie", use the **Still/Movie/S&Q** button.

## What changed after the first test

The first test applied all five steps cleanly; the camera restarted the moment movie mode started. The coprocessor keeps its log across such a restart, and its last entry is a deliberate stop: the picture pipeline's first stage never started, the firmware reset the sensor 11 times, then forced the restart. The A7 IV did exactly this before its open gate worked.

- **The cause: the raw write buffer.** In movie mode the camera writes each raw frame into one buffer. On the ZV-E1 that buffer holds 4288 × 2408 bytes, just the stock 4K frame. The A7S III gives the same buffer 26,214,400 bytes. The full-height frame needs 4288 × 2848, so the ZV-E1 refused it and the first stage never started.
- **New first step, L13:** one word of the coprocessor's memory manager gives that buffer the A7S III's size. It is checked in the ZV-E1's own allocator code (run in emulation). It must be written before movie mode is entered after a cold boot: if a movie buffer is open, the step writes nothing and says so.
- **Sensor step L5 is now `ogsq_zv_v2`:** two bytes of the stored drive-parameter record (+0x129, +0x15e) were left at stock in v1 (a guess). They now hold the calculated values. The camera's own run-time bytes, which the first test's dumps showed at +0x11a/+0x11b, are not touched.
- **The closing session's order:** the Still/Movie/S&Q button does nothing while the camera is connected as a USB drive. So: unplug, switch to movie, look at the screen, plug in again.
- **`check_readonly` must be run again** with this version: it now also reads the buffer size, and the apply only accepts a check from this version.

Two things from the first report are harmless: the `!! read failed -21` lines (`/proc/driver/pcie/...` entries that are folders on this body), and the camera briefly showing on macOS as a USB HID device (`054C:096F`) when service mode ends.

## Tested on a ZV-E1

One ZV-E1, firmware 2.02, macOS, kit version 2 (`8feaae7`): `check_readonly` said READY, and the six-step `open_gate_apply` ran twice, each time after a battery pull; every step said DONE.

| What | Result |
|---|---|
| XAVC HS 4K 24p (23.976p), open gate | Works: 3840 × 2560 HEVC 10-bit 4:2:0, about 50 Mbps (clips of 25.5 s and 8 s; no recording failed) |
| Field of view | Same width as stock 4K; about 204 rows more above and 196 below (a stock and an open-gate clip from the same spot match at scale 1.000) |
| C2 preview cycle | Works as described |
| SteadyShot Standard / Active / Dynamic Active | Work |
| Focus peaking | Works |
| MP4 header height (step M19), XAVC HS 4K 24p | Works. `open_gate_apply` with M19 run three times from a battery pull: all six steps DONE each time. The stream, tkhd, the `hvc1` sample entry and Sony's VPRF all say 3840 × 2560; Sony's XML still says `HEVC_3840_2160`. The clips show at 3:2 on a Mac without any fix (and earlier, with the same two instructions written by a separate helper, DaVinci Resolve imported them as 3840 × 2560) |
| `open_gate_putback`, same power-on | Works. With the preview at 3:2 first: C20, S17, M20, L17, L6, L14 all DONE; M20 wrote back 107 sites (101 av-cam.bin, the four libmpr.so rows and the two header instructions). The next XAVC HS 4K 24p clip was a plain 3840 × 2160 file with 3840 × 2160 headers |
| Power switch off and on (battery in) | Mixed state: coprocessor sites stock, encoder sites still applied (see above). One 4K 24p clip: a 3840 × 2560 file, the 16:9 picture letterboxed with 200 black rows above and below, headers 3840 × 2560. XAVC S HD 1920 × 1080 23.98p and S&Q (59.94 capture, 29.97 file, 1920 × 1080) recorded normally, with 1920 × 1080 streams and headers. C2 in movie mode did nothing (no preview cycle, no Step zoom). A plain 3840 × 2160 clip from an earlier session (kit version 2 as published) was most likely recorded after a battery pull, not only the power switch (not logged), so it does not contradict this |
| Battery pull | Everything back to stock, header height included. Tested with M19: after a fresh apply (open-gate clip 3840 × 2560 in stream and headers), battery out for 10 seconds, then `check_readonly`: every coprocessor site, the four libmpr.so rows and all 101 av-cam.bin sites stock, VERDICT READY. The next XAVC HS 4K 24p clip was a plain 3840 × 2160 file with 3840 × 2160 headers |

**Known issues (reported on [issue #1](https://github.com/ArcaneLantern/zve1-open-gate-test/issues/1); this change does not touch them):**

- **60p:** the live view is garbage, and starting a recording crashes the camera (seen again with this version). Pressing record at 4K 59.94p also crashed and restarted the camera in the mixed state after a power switch; after that restart C2 did Step zoom again and 4K clips (60p and 24p) were plain 3840 × 2160 files. Stay at 24p.
- **Live view after the apply:** sometimes a purple cast with a garbled strip at the bottom when movie mode is entered; some applies come up clean. Starting a recording fixes it, and it stays fixed. Going from playback to live view, or from photo to video, gives a brief purple flash about half the time.
- **Focus / tracking frame:** works, but looks stretched vertically (the 16:9 frame geometry scaled to 3:2). Cosmetic.

**Not tested yet:** `open_gate_putback`, or a second `open_gate_apply`, after a power switch; open gate in XAVC S 4K (with or without the header height); `--no-meta`; `open_gate_apply_no_screen` with the header step; in-camera playback of a clip with the new headers; Proxy Recording (the A7 IV kit says to turn it off; do so here too); 25p; Gyroflow and Catalyst Browse with these files. The two header instructions are the MP4 writer's only 3840-wide cases (one for AVC, one for HEVC), not one per record setting; two of the writer's cases share each instruction, and which record settings use the second ones (for example an AVC intra setting) has not been checked.

**What the A7S III showed, which may or may not happen here:**

- The live view was glitchy (purple, lower part black) whenever movie mode was entered from stills. Starting and stopping a short recording fixed it until the next visit to stills. The recorded file was always right.
- 60p distorted the picture and crashed the camera while the patch was applied.
- The power switch removed the patch.

| Launcher (`windows/` `.cmd`, `macos/` `.command`) | What it does | Writes to the camera? |
|---|---|---|
| `check_readonly` | Confirms the camera runs the 2.02 software the port was made from, and reads what every patch site holds. Verdict READY / NOT READY | No |
| `dump_info` | The same, plus facts for the port: the camera's logs, sensor register state, internal tables, the display tables | No |
| `open_gate_apply` | Applies the state in six steps (the raw write buffer, open gate with the MP4 header height, the screen at 3:2, the C2 preview), then one read-only session. `--no-meta`: without the header height | **Yes: memory only** |
| `open_gate_apply_no_screen` | Only the four open-gate steps (the raw write buffer and the three open-gate steps, with the MP4 header height; `--no-meta` as above) | **Yes: memory only** |
| `open_gate_putback` | Puts the six steps back, the MP4 header height included (also after an apply with `--no-meta`) | Yes: memory only |
| `screen_putback` | Puts the two screen steps back | Yes: memory only |

Nothing in this kit writes to the camera's firmware or to its settings.

## Before you start

1. The camera's menu must show **Ver. 2.02** (Setup, Setup Option, Version). On any other version, stop and tell us the version.
2. **USB Connection Mode: Mass Storage.** If asked on connection, choose **Image Transfer (MSC)**.
3. A charged battery. Do not record or play back while a step runs.
4. **Run `check_readonly` first.** The apply refuses to start until a check on your camera has said READY.

## Windows, once

1. Install Python 3.10 or later from python.org (with the "py launcher").
2. Run `windows/setup.cmd`.
3. Install the libusb-win32 driver for the camera with [Zadig](https://zadig.akeo.ie): Options, List All Devices, pick the camera, choose libusb-win32, Replace Driver. The first run switches the camera to service mode, where it shows up as a new device (054C:0336): install the driver for that one too, then run the step again.

## macOS, once

1. Python 3.9 or later: the one macOS offers with the Xcode Command Line Tools (run `xcode-select --install` in Terminal) works, or install it from python.org.
2. Double-click `macos/setup.command`. No Homebrew and no driver are needed.
3. Use the `.command` launchers in `macos/`, which match the Windows ones.

Each live run asks for your Mac password. macOS keeps its own driver on the camera's USB connection, and only an administrator can hand the camera over to the script. The script unmounts the camera's memory card first and does not erase anything on it.

If macOS refuses to open a .command file, open System Settings > Privacy & Security and click "Open Anyway". Or, in Terminal, type `bash` and a space, drag the file in, and press Return.

## Android

`android/ZVE1-OpenGate.apk` runs the same files from a phone connected by USB-C (or an OTG adapter). Only the USB access, the dialogs and the folder for the results are the phone's.

1. Install the APK (allow installing from unknown sources). Set the camera's **USB Power Supply to Off**, or it charges from the phone.
2. Press **1. Read-only check**, then **2. Apply to camera**. The app as published carries the tools from before the MP4 header height: its files say 3840 × 2160 in the headers until the app is rebuilt. The "Screen steps" box chooses between six steps (ticked) and four. Use app version 0.2 or later (0.1 is the first version of the kit).
3. When Android asks to open *ZV-E1 Open Gate* for the camera, tick **Always**. It asks twice: once for Mass Storage, once for service mode.
4. When the log says **unplug and plug in again**, do that with the phone cable. Never switch the camera off.
5. Afterwards, press **Export logs**. It writes a zip to `Download/ZVE1-OpenGate/`: send that zip back.

**Self-test** and **Dry run** need no camera.

## Running it

1. In the menu, set File Format XAVC S 4K (or XAVC HS 4K) and 24p. APS-C/Super 35 off, S&Q off, Proxy Recording off.
2. Pull the battery for 10 seconds, put it back, and switch on, in **stills** mode. **Do not go into movie mode yet**: step 1 refuses if a movie buffer has been opened since the camera was switched on.
3. Connect USB and run `check_readonly`. Send the folder back if it does not say READY.
4. Run `open_gate_apply`. It asks for the firmware version and a typed YES. It runs six steps.
5. Between steps it asks you to **unplug and replug the USB cable. Do not switch the camera off and do not pull the battery** until it says it is finished.
6. At the end, it asks for one more session, which only reads: **unplug**, press the Still/Movie/S&Q button until the camera is in **movie** mode, look at the rear screen for five seconds, then **plug in again** (still in movie mode). The script runs the read-only dump itself.
7. When it says so, unplug. Record 20 to 30 seconds, stop, and play the clip back.
8. To return to stock, pull the battery for 10 seconds, or run `open_gate_putback` with the preview at 3:2.

**While it is applied:** use only XAVC HS 4K or XAVC S 4K at 24p. Other formats, frame rates, S&Q and APS-C/Super 35 are likely to fail or hang. 60p crashed the camera when a recording started.

**After switching off and on with the power switch:** the camera can be left in a mixed state, sensor side stock and encoder side (with the header height) still at 2560. In that state a 4K clip came out as a 3840 × 2560 file with the 16:9 picture letterboxed, and 60p crashed the camera. Pull the battery for 10 seconds before recording normal 4K again (`open_gate_putback` clears the encoder side in the same power-on; after a power switch it has not been tried). To shoot open gate again, pull the battery and run `open_gate_apply` again from stills mode.

## Please send back

- The zipped `windows/camera_private` folder, or the phone's export zip.
- What the screen showed between the unplug and the replug of step 6, and after it.
- The clip's size and frame rate (3840 × 2560, 23.976?), and whether the picture shows the whole sensor height (compare with a photo).
- What each C2 press shows, and whether the focus frames sit on the picture.
- Whether the live view is glitchy when you go from stills to movie, and whether a short recording fixes it.
- **One check after a power-off:** switch off and on with the power switch (no battery pull), stills mode, run `check_readonly`, and include that folder. On a ZV-E1 the check after a power switch read the coprocessor sites as stock and the encoder sites as applied.

**If the camera misbehaves** (grey lines, flicker, restart, freeze, recording that stops by itself), and it still responds: don't pull the battery yet. Switch to stills, connect USB, run `dump_info`, send the folder, and then pull the battery. If it does not respond, just pull the battery.

## If something stops

Every stop prints a reason, and says either "Nothing was sent" or what was sent. Please send that text.

- *the camera is in service mode but that device has no libusb driver yet*: this is expected on the first Windows run. Do the Zadig step for the new device and run again.
- *DeviceInfo.xml is not the file of the 2.02 update*: the camera has other firmware. Nothing further is sent.
- *VERDICT NOT READY*: something on the camera is not as the 2.02 files predict. Send the folder; the apply will not start.
- *STOPPED at step 1 (L13): nothing was written*: most likely the camera has been in movie mode since it was switched on. Pull the battery for 10 seconds, switch on in stills mode, and run the apply again.
- *the newest saved read-only check ... does not say READY*: a check from the first version of the kit does not count. Run `check_readonly` again.

## What is in here

- `windows/`: the launchers, `setup.cmd`, and `tools/` (the scripts, the pinned program files and their source, the patch designs, and in `tools/modding/zve1` the builders and the C2 routine's source). `ogfile2560_hs_s_zv_v2` is the encoder design with the MP4 header height (steps M19 / M20); `ogfile2560_hs_s_zv_v1` without it (L19 / L20, `--no-meta`).
- `macos/`: `setup.command` and the `.command` launchers; they run `windows/tools`.
- `android/ZVE1-OpenGate.apk`: the phone app, carrying `windows/tools` as published here.
- `PORT_NOTES.md`: how the A7S III kit maps onto the ZV-E1, what is the same, what differs, and what is guessed.

Built on [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) (vendored under `windows/tools/third_party`, MIT licence).
