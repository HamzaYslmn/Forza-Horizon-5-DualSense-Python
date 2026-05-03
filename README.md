> Steam profile: <https://steamcommunity.com/id/teccno/>
>
> I do not own Forza Horizon 6 yet, so if you appreciate this project, you can gift it to me. Have fun using the app.

<div align="center">
  <h1>🏎️ Forza Horizon 5 — DualSense Adaptive Triggers</h1>
  <p><strong>Real, physics-driven trigger feedback for the Steam version of FH5.</strong></p>
  <p><em>Lightweight · No presets · No mode juggling · One file of knobs you can edit in 10 seconds.</em></p>
</div>

---

## TUI Screenshot
![alt text](img/tui.png)

## 📜 Table of Contents
1. [Why this exists](#-why-this-exists)
2. [What you'll feel](#-what-youll-feel)
3. [How it works](#-how-it-works)
4. [Installation](#%EF%B8%8F-installation)
5. [In-game setup](#-in-game-setup)
6. [Run it](#%EF%B8%8F-run-it)
7. [CLI options](#%EF%B8%8F-cli-options)
8. [Tuning the feel](#%EF%B8%8F-tuning-the-feel)
9. [Project layout](#-project-layout)
10. [Troubleshooting](#-troubleshooting)
11. [Credits](#-credits)

---

## 💡 Why this exists

Forza Horizon 5 on PC sends rich telemetry over UDP — but Steam Input only forwards generic rumble to the DualSense. The actual **adaptive triggers** (the killer feature of the controller) just sit there doing nothing.

This project bridges the gap with a tiny Python service:

- It reads FH5's UDP packets each frame.
- It computes a single adaptive-trigger command for each trigger.
- It writes those commands to the DualSense via raw HID — **without touching the rumble bits**, so Steam keeps doing its job.

The result: a brake pedal that feels like a brake pedal and a gas pedal that pushes back when the engine is working.

---

## 🎮 What you'll feel

### Left trigger — Brake
A **continuous, exponential** brake resistance. The trigger keeps a tiny always-on baseline so it does not rapidly toggle between off and rigid near the deadzone. As brake input rises, resistance climbs softly at first and gets firmer near the end.

Left-trigger effects:

| Priority | Effect | Feel |
|---------:|--------|------|
| 1 | **ABS / tire-slip pulse** | A fast `35 Hz` vibration when braking hard enough, moving above the minimum speed, and tire slip telemetry crosses the ABS thresholds. |
| 2 | **Progressive brake resistance** | Exponential rigid resistance from a `1`-force baseline up to `25` during normal braking. Above ~98% input it jumps to full trigger force (`255`). |
| 3 | **Handbrake bonus** | Adds a flat `25` force on top of the normal brake resistance when the handbrake is engaged. |

### Right trigger — Throttle
Strict priority — **only one effect plays at a time**, so animations never fight:

| Priority | Effect | Feel |
|---------:|--------|------|
| 1 | **Gear-shift thump** | A short `20 Hz` vibration burst (~100 ms) when shifting up or down while the car is moving. |
| 2 | **Rev limiter buzz** | A `30 Hz` vibration when RPM is above the redline ratio. |
| 3 | **Progressive throttle resistance** | Soft exponential resistance from a `1`-force baseline up to `10` during normal throttle. Above ~98% input it jumps to full trigger force (`255`). |

The chain lives in [TriggerAnimation._throttle()](src/modules/dualsense/triggers.py) — about 20 lines, easy to extend.

---

## ⚡ How it works

```
┌──────────────┐   UDP 5300    ┌──────────────┐   HID write    ┌─────────────┐
│  Forza H5    │ ────────────► │  fh5ds.py    │ ─────────────► │  DualSense  │
│  Data Out    │   324 bytes   │  per frame   │  triggers only │  controller │
└──────────────┘               └──────────────┘                └─────────────┘
                                      │
                                      ▼
                           Steam Input keeps owning rumble
```

- **UDP listener** ([modules/udplistener/main.py](src/modules/udplistener/main.py)) parses FH5's 324-byte telemetry packet (RPM, speed, accelerator, brake, gear, drivetrain…). Each frame it **drains the socket and uses only the latest packet**, so we never react to stale telemetry if the OS queues bursts.
- **TriggerAnimation** ([modules/dualsense/triggers.py](src/modules/dualsense/triggers.py)) turns telemetry into a `(left, right)` tuple of trigger commands.
- **DualSense HID layer** ([modules/dualsense/main.py](src/modules/dualsense/main.py)) writes them out, flipping only the trigger bits in `valid_flag0` so Steam's rumble bytes stay untouched. The HID device is opened in **non-blocking mode** so writes fire immediately instead of waiting for an input report (important on Bluetooth).

---

## 🛠️ Installation

**Requirements:** Windows, Python 3.10+, and a DualSense controller (USB or Bluetooth).

### Option 1: Start with `start.bat`

Download or clone the project, then double-click `start.bat` in the project folder:

```text
start.bat
```

The launcher does the setup work for you:

- It checks whether `uv` is installed.
- If `uv` is missing, it asks before downloading/installing it.
- Press `Y` or Enter to install `uv` with the official Astral installer.
- Press `n` to install `uv` with `python -m pip install uv` instead.
- After `uv` is available, it enters the `src` folder and runs `uv run main.py`.

Use this option if you just want to launch the app on Windows.

### Option 2: Manual installation

Clone the repository:

```bash
git clone https://github.com/HamzaYslmn/Forza-Horizon-5-DualSense-Python
cd Forza-Horizon-5-DualSense-Python
```

Install `uv` if you do not already have it:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Or install it with pip:

```bash
python -m pip install uv
```

Then install/sync the Python environment from the `src` folder:

```bash
cd src
uv sync
```

---

## 🎯 In-game setup

Open Forza Horizon 5 → **Settings → HUD and Gameplay**, scroll to the bottom:

| Setting | Value |
|---------|-------|
| Data Out | **ON** |
| Data Out IP Address | **127.0.0.1** |
| Data Out IP Port | **5300** |

<p align="center">
  <img src="img/en.png" alt="English Settings" width="48%" style="border-radius: 8px;">
  &nbsp;
  <img src="img/tr.png" alt="Turkish Settings" width="48%" style="border-radius: 8px;">
</p>

---

## ▶️ Run it

### Option A: Manual Launch
Run the script from the terminal:
```bash
cd src
uv run main.py
```

Or just double-click the `start.bat` file. 

You should hear a brief startup pulse on both triggers — that confirms HID writes are landing on the controller. After that, fire up FH5 and start driving.

> Run the script **before or while FH5 is loading**. Steam Input must be active for the controller; if you use HidHide, allowlist `python.exe`.

### Option B: Start via Steam (Auto Launch)
You can configure Steam to launch the DualSense script automatically in the background whenever you press **Play** on Forza Horizon 5.

1. Open Steam, right-click **Forza Horizon 5** in your Library -> **Properties**.
2. In the **General** tab, scroll down to **Launch Options**.
3. Paste the following line exactly (update the path to wherever you downloaded this project):
   ```text
   cmd /c "start /MIN /D C:\Your\Path\To\Forza-Horizon-5-DualSense-Python\src uv run main.py" && %command%
   ```

Now, whenever you start the game from Steam, the Python script will quietly launch in a minimized window just before the game opens. No `.bat` files needed!

---

## ⚙️ CLI options

The defaults work for almost everyone. Use these only if you need them.

| Argument | Description | Default |
|----------|-------------|---------|
| `--host` | UDP bind address | `127.0.0.1` |
| `--port` | UDP port | `5300` |
| `--debug` | Verbose per-packet logging | off |

Example:
```bash
cd src
uv run main.py --port 5400 --debug
```

---

## 🎚️ Tuning the feel

Open [src/modules/settings.py](src/modules/settings.py) and edit any field. There are **no presets, no multipliers, no inheritance** — just one flat dataclass. Changes take effect on next launch.

Every trigger effect has an `enable_*` switch. Set it to `False` if you do not want that effect.

### Brake (left trigger)

| Field | Default | Effect |
|-------|--------:|--------|
| `enable_brake_resistance` | `True` | Toggle the normal progressive brake resistance. |
| `brake_baseline_force` | `1` | Always-held resistance. Prevents off↔rigid jitter near the deadzone. |
| `brake_max_force` | `25` | Normal brake resistance before the full-press threshold. |
| `brake_curve` | `2.5` | Higher = softer early press and sharper resistance near the end. |
| `enable_handbrake_bonus` | `True` | Toggle the extra handbrake force. |
| `handbrake_bonus` | `25` | Flat extra rigid force when the handbrake is engaged. |
| `brake_deadzone` | `10` | Ignore brake input below this raw value (out of 255). |
| `pedal_full_force_at` | `248` | Pedal value where the trigger jumps to full force (`255`). |

### ABS / tire slip (left trigger)

| Field | Default | Effect |
|-------|--------:|--------|
| `enable_abs` | `True` | Toggle the ABS-like tire-slip vibration. |
| `abs_brake_threshold` | `80` | Minimum brake input required before ABS can activate. |
| `abs_min_speed_kmh` | `15.0` | Minimum speed required before ABS can activate. |
| `abs_slip_ratio_threshold` | `1.0` | Tire slip ratio threshold for ABS vibration. |
| `abs_combined_slip_threshold` | `1.0` | Combined tire slip threshold for ABS vibration. |
| `abs_freq` | `35` Hz | ABS pulse frequency. |
| `abs_amp` | `255` | ABS pulse amplitude (0-255). |

### Throttle (right trigger)

| Field | Default | Effect |
|-------|--------:|--------|
| `enable_throttle_resistance` | `True` | Toggle the normal progressive throttle resistance. |
| `throttle_baseline_force` | `1` | Always-held resting weight. Prevents off↔rigid jitter near the deadzone. |
| `throttle_max_force` | `10` | Normal throttle resistance before the full-press threshold. Kept softer than the brake. |
| `throttle_curve` | `5.2` | Higher = much softer light throttle, with resistance arriving late in the press. |
| `accel_deadzone` | `10` | Ignore tiny accelerator noise. |
| `pedal_full_force_at` | `248` | Pedal value where the trigger jumps to full force (`255`). |

### Throttle effects

| Field | Default | Effect |
|-------|--------:|--------|
| `enable_gear_shift` | `True` | Toggle the shift thump. |
| `gear_shift_freq` | `20` Hz | Lower = deeper thump, higher = sharper click. |
| `gear_shift_amp` | `255` | Max amplitude (0–255). |
| `gear_shift_duration_ms` | `100.0` | How long the burst lasts. |
| `enable_rev_limiter` | `True` | Toggle the rev limiter buzz. |
| `rev_limit_ratio` | `0.95` | Buzz when `rpm / max_rpm` exceeds this. |
| `rev_limit_freq` | `30` Hz | Buzz frequency. |
| `rev_limit_amp` | `255` | Buzz amplitude. |

### Connection / system

| Field | Default | Effect |
|-------|--------:|--------|
| `udp_host` | `"0.0.0.0"` | UDP bind address. |
| `udp_port` | `5300` | UDP port (must match FH5). |
| `udp_timeout` | `0.5` s | Listener timeout (used to detect "no telemetry"). |
| `enable_startup_pulse` | `True` | Toggle the short trigger pulse on app startup. |
| `startup_pulse_force` | `150` | Strength of the connect-confirm pulse. |

---

## 📁 Project layout

```
src/
├── main.py                          # Entry point: arg parsing, packet loop
└── modules/
    ├── settings.py                  # 👈 the only file you usually edit
    ├── dualsense/
    │   ├── main.py                  # HID layer (rumble bits left untouched)
    │   └── triggers.py              # Effect primitives + TriggerAnimation
    └── udplistener/
        └── main.py                  # UDP socket + 324-byte packet parser
```

---

## 🩺 Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `DualSense gamepad interface not found` | Controller not connected, or HidHide is hiding it. Allowlist `python.exe` in HidHide. |
| `No UDP packets yet` after several seconds | FH5 Data Out is off, IP/port mismatch, or Windows Firewall is blocking the bind. |
| Triggers feel weak | Increase `brake_max_force` / `throttle_max_force`, or lower the relevant `curve` for earlier resistance. Values above `pedal_full_force_at` still jump to full force (`255`). |
| Triggers feel like a rock wall before pedal hits 100% | Lower `brake_max_force` / `throttle_max_force`, or raise the relevant `curve` so resistance arrives later. |
| Triggers feel too stiff at light press | Lower the relevant baseline force, or raise the relevant `curve` for a softer initial press. |
| Brake "machine-guns" / buzzes when barely pressed | This was the original off↔rigid jitter — already fixed by the always-held baseline. If it returns, raise the deadzone or the baseline force. |
| No vibration on gear shift | Make sure the car is moving faster than 3 km/h and the change is between valid gears. Neutral/invalid gear transitions are intentionally ignored. |

---

## 🙏 Credits

Built by **[HamzaYslmn](https://github.com/HamzaYslmn)**.

---
*Built for an immersive racing experience — KISS code, real feedback.*
