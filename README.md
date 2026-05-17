<div align="center">
  <h1>🏎️ Forza Horizon — DualSense Adaptive Triggers</h1>
  <p><strong>Real trigger feedback for Forza Horizon on PC.</strong></p>
  <p><em>Feel the brakes. Feel the engine. No setup juggling.</em></p>
</div>

![TUI Screenshot](img/tui.png)

> 💛 Huge thanks to **[Jared (jmac122)](https://github.com/jmac122)** for sponsoring this project by gifting me Forza Horizon 6.
>
> Steam profile: <https://steamcommunity.com/id/teccno/>

---

## 📜 Contents
1. [What it does](#-what-it-does)
2. [Install](#-install)
3. [In-game setup](#-in-game-setup)
4. [Run it](#-run-it)
5. [Auto-launch with Steam](#-auto-launch-with-steam)
6. [Tuning the feel](#-tuning-the-feel)
7. [Troubleshooting](#-troubleshooting)
8. [Credits](#-credits)



---

## 💡 What it does

Forza Horizon sends car telemetry over UDP, but Steam Input doesn't use the DualSense's **adaptive triggers**. This tiny app fills the gap:

- **Left trigger (brake)** — pushes back harder the more you press. Buzzes like ABS when tires slip. Extra resistance when handbraking.
- **Right trigger (throttle)** — soft progressive resistance. Thumps on gear shifts. Buzzes at the rev limiter.

### How it talks to your controller without fighting Steam

```
┌──────────────────┐    UDP 5300     ┌──────────────────┐    HID write    ┌─────────────┐
│  Forza Horizon   │ ──────────────► │  This app        │ ──────────────► │  DualSense  │
│  (Data Out)      │  telemetry      │  (trigger bits   │  triggers only  │  controller │
└──────────────────┘  324 bytes      │   only)          │                 └─────────────┘
                                     └──────────────────┘                        ▲
                                                                                 │
                                     ┌──────────────────┐    HID write           │
                                     │  Steam Input     │ ──────────────────────►│
                                     │  (rumble bits)   │  rumble + buttons      │
                                     └──────────────────┘
```

Both the app and Steam write to the same controller — but they touch **different bytes**:

- Steam owns the **rumble motors** and button mapping.
- This app only flips the **adaptive trigger** bits (`valid_flag0` bits `0x04` and `0x08`).
- The HID device is opened in **non-blocking mode**, so writes fire immediately instead of waiting on the controller. Nothing gets queued, nothing blocks Steam.

That's why you can run both at the same time and neither one breaks the other.

---

## 🛠️ Install

**You need:** Windows 10/11 or Linux, and a DualSense controller (USB or Bluetooth).

1. Go to the [latest release](https://github.com/HamzaYslmn/Forza-Horizon-DualSense-Python/releases/latest).
2. Download **`win_start.bat`** (Windows) or **`linux_start.sh`** (Linux).
3. Put it in any empty folder and double-click it.

The launcher handles everything: downloads the app, installs Python if needed, and runs it. Next time you run it, it checks for updates.

> **Linux extras:** install `libhidapi` (`sudo apt install libhidapi-hidraw0` / `sudo pacman -S hidapi` / `sudo dnf install hidapi`) and the udev rule from `app/packaging/linux/70-dualsense.rules`. Then unplug/replug the controller once.

<details>
<summary>Manual install (for developers)</summary>

```bash
git clone https://github.com/HamzaYslmn/Forza-Horizon-DualSense-Python
cd Forza-Horizon-DualSense-Python/src
uv sync
uv run main.py
```

Need `uv`? `pip install uv` or [astral.sh/uv](https://astral.sh/uv/).
</details>

---

## 🎯 In-game setup

In Forza Horizon, open **Settings → HUD and Gameplay** and scroll to the bottom:

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

Double-click **`win_start.bat`** (Windows) or **`linux_start.sh`** (Linux).

You'll feel a short pulse on both triggers — that means it's working. Now launch Forza Horizon and drive.

> Start the launcher **before** Forza Horizon. If you use HidHide, allowlist `python.exe`.

---

## 🎮 Auto-launch with Steam

Want the triggers to turn on automatically when you press **Play**? Tell Steam to run the launcher first.

1. In Steam, right-click **Forza Horizon** → **Properties**.
2. Open the **General** tab and find **Launch Options**.
3. Paste this (change the path to where your `win_start.bat` actually is):

   ```text
   "C:\Your\Path\To\Forza-Horizon-DualSense-Python\win_start.bat" %command%
   ```

That's it. Press **Play** — the launcher runs, then the game opens.

![Steam launch options](img/steaming.png)

<details>
<summary>Advanced — run the Python script directly (no BAT file)</summary>

If you cloned the repo and use `uv`, paste this into **Launch Options** instead:

```text
cmd /c "start /MIN /D C:\Your\Path\To\Forza-Horizon-DualSense-Python\src uv run main.py" && %command%
```
</details>

---

## 🎚️ Tuning the feel

Every effect (brake force, ABS buzz, gear thump, rev limiter, etc.) can be tweaked or turned off from the **Settings page in the app** — no file editing needed. Changes apply on next launch.

> ⚠️ The rev limiter fires based on `rpm / max_rpm`, not a fixed RPM. Different cars hit redline at different ratios, so it may need per-car tweaking.

---

## 🩺 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `DualSense gamepad interface not found` | Controller not connected, or HidHide is hiding it — allowlist `python.exe`. |
| `No UDP packets yet` | Forza's Data Out is off, IP/port is wrong, or Windows Firewall is blocking. |
| Triggers feel weak | Raise `brake_max_force` / `throttle_max_force`, or lower the matching `curve`. |
| Triggers feel like a brick wall | Lower `brake_max_force` / `throttle_max_force`, or raise the matching `curve`. |
| Triggers feel stiff at a light press | Lower the baseline force, or raise the `curve`. |
| No vibration on gear shift | Car must be moving faster than 3 km/h and changing between valid gears. |
| Console window is blank after the startup pulse | Run from a terminal with `cd src && uv run main.py --no-tui` to skip the TUI. |

---

## 📁 Project layout

```
src/
├── main.py                          # Entry point
└── modules/
    ├── settings.py                  # 👈 the file you edit
    ├── dualsense/
    │   ├── main.py                  # HID layer
    │   └── triggers.py              # Effect logic
    └── udplistener/
        └── main.py                  # UDP parser
```

---

## 🙏 Credits

Built by **[HamzaYslmn](https://github.com/HamzaYslmn)**.

### 💛 Sponsors

- **[Jared (jmac122)](https://github.com/jmac122)** — gifted me Forza Horizon 6 so this project could keep moving forward. Thank you, Jared!
- **[BambinoPinguino](https://github.com/BambinoPinguino)** — thank you for your Tea!

---
*Built for an immersive racing experience*
