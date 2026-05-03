# AGENTS.md — Onboarding for New Developers

A short tour of the project so you can read, run, and modify it in an afternoon.

---

## 1. What is this project?

A small Python service that gives the **PlayStation DualSense controller real
adaptive‑trigger feedback while playing Forza Horizon 5 on PC (Steam)**.

- Forza Horizon 5 broadcasts live telemetry (RPM, speed, pedals, tire slip, gear…)
  over **UDP** if you turn on **HUD & Gameplay → Data Out** in the game.
- Steam Input only sends generic rumble to the DualSense; the trigger motors
  do nothing.
- This project listens to the UDP feed, computes a trigger force/vibration
  every frame, and writes it directly to the controller via **raw HID**, while
  carefully **not touching the rumble bytes** so Steam still drives rumble.

Result: brake trigger that resists like a brake pedal, throttle trigger that
pushes back when the engine works, ABS pulse on tire slip, gear‑shift thump,
rev‑limiter buzz.

---

## 2. Tech stack

| Piece | What |
|---|---|
| Language | Python (project requires `>=3.14`, see `src/pyproject.toml`) |
| Package manager | [`uv`](https://astral.sh/uv) (fast, replaces pip + venv) |
| Single dependency | [`hidapi`](https://pypi.org/project/hidapi/) for raw HID I/O |
| OS | Windows (HID layer + `start.bat` are Windows‑specific) |
| Hardware | DualSense or DualSense Edge over USB or Bluetooth |

No tests, no CI, no linter run automatically. `ruff` line length is set in
`pyproject.toml` but not enforced.

---

## 3. Repository layout

```
Forza-Horizon-5-DualSense-Python/
├── README.md            # User‑facing docs (install, in‑game setup, tuning)
├── AGENTS.md            # ← you are here (developer onboarding)
├── LICENSE
├── start.bat            # Windows launcher: installs uv if missing, runs main.py
├── img/                 # Screenshots used in README
├── .github/FUNDING.yml  # GitHub sponsorship config
└── src/
    ├── pyproject.toml   # Project metadata + dependencies
    ├── uv.lock          # Locked dependency versions (do not edit by hand)
    ├── main.py          # Entry point: arg parsing + main packet loop
    └── modules/
        ├── __init__.py        # Exposes setup_logging() + sub‑packages
        ├── settings.py        # 👈 ALL tunables live here (one dataclass)
        ├── dualsense/
        │   ├── __init__.py    # Re‑exports DualSense, TriggerAnimation, triggers
        │   ├── main.py        # HID layer (open/close/write to controller)
        │   └── triggers.py    # Effect primitives + per‑frame TriggerAnimation
        └── udplistener/
            ├── __init__.py    # Re‑exports UDPListener, parse_packet
            └── main.py        # UDP socket + 324‑byte FH5 packet parser
```

The whole codebase is **~6 small files**. Read them in this order:

1. `src/main.py`
2. `src/modules/settings.py`
3. `src/modules/udplistener/main.py`
4. `src/modules/dualsense/triggers.py`
5. `src/modules/dualsense/main.py`

---

## 4. How the data flows (one frame)

```
Forza Horizon 5  ──UDP 5300, 324 bytes──►  UDPListener.recv_latest()
                                                  │
                                                  ▼
                                          parse_packet(pkt) -> dict
                                                  │
                                                  ▼
                                  TriggerAnimation.update(t, settings)
                                                  │
                                                  ▼
                                       (left, right) trigger commands
                                                  │
                                                  ▼
                                            DualSense.set(left, right)
                                                  │  (worker thread writes HID
                                                  │   only when state changes)
                                                  ▼
                                          DualSense controller motors
```

Each trigger command is a 3‑tuple `(mode, p1, p2)`:
- `M_OFF (0x05)` — trigger free
- `M_RIGID (0x01)` — constant resistance, p2 = force 0..255
- `M_PULSE (0x06)` — vibration, p1 = freq Hz, p2 = amplitude 0..255

The HID write only flips `valid_flag0` bits for the trigger motors, so Steam
Input keeps owning the rumble bytes.

---

## 5. The five files in detail

### `src/main.py` — entry point
- Parses CLI args (`--host`, `--port`, `--debug`, optional trailing `game_cmd`).
- Builds a `Settings()` and overrides host/port from CLI.
- Calls `run(settings, game_cmd)` which:
  1. Opens the `DualSense` (HID write thread + optional startup pulse).
  2. Opens a `UDPListener` context manager.
  3. Enters `_loop`: pull latest packet, parse, compute trigger output,
     write only when it changes, log a debug line once per second.
- If `game_cmd` is passed (Steam wrapper mode), spawns the game as a child
  process and exits when the game exits.

### `src/modules/__init__.py` — logging
- One helper: `setup_logging(debug)`. ANSI‑colored output on Windows, level
  switches between INFO and DEBUG.

### `src/modules/settings.py` — the only file most users edit
- A single `@dataclass Settings` with **flat fields** (no presets, no
  inheritance). Forces are 0..255, frequencies are Hz.
- Each effect has an `enable_*` switch. See README §"Tuning the feel" for
  field‑by‑field meaning.

### `src/modules/udplistener/main.py`
- `parse_packet(p)`: unpacks the 324‑byte FH5 telemetry into a dict
  (RPM, accel, brake, gear, speed in km/h, four‑wheel slip values, etc.).
  Format follows Forza Motorsport's "Data Out" spec.
- `UDPListener` (context manager): binds a UDP socket with a tiny receive
  buffer and `recv_latest()` returns **only the freshest queued packet** so we
  never react to stale telemetry under load.

### `src/modules/dualsense/triggers.py`
- Effect primitives: `off()`, `rigid(force)`, `vibration(freq, amp)`.
- `TriggerAnimation.update(t, s)` returns `(left, right)` each frame.
  - **Left (brake):** ABS slip pulse → progressive rigid resistance with
    optional handbrake bonus.
  - **Right (throttle), strict priority:** gear‑shift burst →
    rev‑limiter buzz → progressive rigid resistance.
- `_pedal_force()` is a baseline → max exponential ramp; pedal values above
  `*_full_force_at` jump straight to 255.

### `src/modules/dualsense/main.py`
- `_find_gamepad()` enumerates HID devices and picks the **Game Pad
  interface** (`usage_page=1`, `usage=5`); the audio/sensor interfaces share
  the same VID/PID and silently drop trigger writes.
- Detects USB vs Bluetooth (different report IDs, sizes, and BT requires a
  CRC32 over the report).
- `DualSense.open()` starts a daemon thread that:
  - drains input reports (non‑blocking) so the BT pipe doesn't stall;
  - writes a new HID report only when `_dirty` (state changed).
- `set(left, right)` is the only API the loop calls.

---

## 6. Running the project

### Quickest path (Windows)
1. `git clone …`
2. Double‑click `start.bat`. It installs `uv` if missing, then `cd src && uv run main.py`.

### Manual
```powershell
# from repo root
cd src
uv sync           # creates .venv and installs hidapi
uv run main.py    # runs the service
```

### CLI flags
| Flag | Meaning |
|---|---|
| `--host` | UDP bind address (default `127.0.0.1`) |
| `--port` | UDP port (default `5300`) |
| `--debug` | Enable per‑packet DEBUG logs |
| trailing args | Optional game command — service exits when game exits (Steam wrapper mode) |

### In‑game setup (must do once)
FH5 → **Settings → HUD and Gameplay → Data Out: ON**, IP `127.0.0.1`,
Port `5300`. See README screenshots in `img/`.

A short pulse on both triggers at startup confirms HID writes are landing.

---

## 7. Common dev tasks

### Tweak the feel
Edit values in `src/modules/settings.py` and relaunch. No code changes needed
for almost any tuning.

### Add a new trigger effect
1. Add an `enable_*` switch + parameter fields to `Settings` in
   `modules/settings.py`.
2. Implement the effect inside `TriggerAnimation._brake()` or `_throttle()`
   in `modules/dualsense/triggers.py`. Mind the **priority order** in
   `_throttle()` — first match wins.
3. If you need a new HID write mode, extend the `M_*` constants and helpers
   in the same file.

### Support a new telemetry field
Add an offset line in `parse_packet()` (`modules/udplistener/main.py`) using
the existing `f/i/b/I/H` helpers; then read it via `t.get("your_field")`
inside `TriggerAnimation`.

### Support another controller / connection mode
HID layout tables `USB` and `BT` in `modules/dualsense/main.py` define
report ID, flag byte position, trigger byte offsets, and report size. Add
a third entry and pick it in `_find_gamepad` / `_is_bluetooth`.

---

## 8. Conventions to keep

- **KISS.** The project is intentionally tiny — no presets, no DI framework,
  no async runtime. Resist the urge to abstract.
- **One file of knobs.** All tunables go in `settings.py`, never inside
  module logic.
- **Don't touch rumble bits.** The HID writer only flips trigger bits in
  `valid_flag0`. Breaking this would fight Steam Input.
- **Always drain UDP.** Use `recv_latest()`; never react to stale packets.
- **Non‑blocking HID.** Trigger writes must not wait on input reports
  (Bluetooth will stall otherwise).
- **State‑change writes only.** The main loop compares `(left, right)` to
  `prev` and only calls `ds.set(...)` when something changed.

---

## 9. Troubleshooting cheat sheet

| Symptom | Cause / fix |
|---|---|
| `DualSense gamepad interface not found` | Controller not connected, or HidHide hides it — allowlist `python.exe`. |
| `No UDP packets yet` after a few seconds | FH5 Data Out off, IP/port mismatch, or Windows Firewall blocking. |
| Triggers feel weak | Raise `brake_max_force` / `throttle_max_force`, or lower the relevant `*_curve`. |
| Triggers feel like a wall | Lower `*_max_force`, or raise `*_curve` so resistance arrives later. |
| "Machine‑gun" buzzing near deadzone | The baseline force prevents it; if it returns, raise `*_baseline_force` or `*_deadzone`. |

See README §"Troubleshooting" for the user‑facing version.

---

## 10. Where to look for what

| You want to… | Open this |
|---|---|
| Change a number / disable an effect | `src/modules/settings.py` |
| Change *how* an effect feels (logic) | `src/modules/dualsense/triggers.py` |
| Touch raw HID bytes | `src/modules/dualsense/main.py` |
| Add a telemetry field | `src/modules/udplistener/main.py` |
| Change CLI / startup wiring | `src/main.py` |
| Change Windows launcher behavior | `start.bat` |

That's the whole project. Welcome aboard.
