"""All tunables in one place. Edit values directly — no presets, no overrides.

Force values are 0–255 (DualSense raw). Frequencies are Hz.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    # --- UDP ---
    udp_host: str = "127.0.0.1"
    udp_port: int = 5300
    udp_timeout: float = 0.5

    # --- Input deadzones (Forza Data Out pedal bytes 0-255) ---
    accel_deadzone: int = 50
    brake_deadzone: int = 50
    pedal_value_max: int = 255
    brake_full_force_at: int = 248  # ~98%; jumps straight to force 255
    throttle_full_force_at: int = 255  # %100; jumps straight to force 255

    # --- Brake (left trigger): exponential ramp baseline -> full press ---
    # Baseline is ALWAYS held (no off()) so the trigger never "machine-guns"
    # by toggling rigid<->off around the deadzone.
    # Normal ramp max stays below 255; above 98% brake uses force 255.
    enable_brake_resistance: bool = True
    brake_baseline_force: int = 0  # constant weight when not pressed
    brake_max_force: int = 5      # normal ramp max below 100% input
    brake_curve: float = 4.1        # >1 = soft early, sharp at the end
    enable_handbrake_bonus: bool = True
    handbrake_bonus: int = 25       # extra rigid when handbrake engaged

    # --- ABS feel from tire slip telemetry (left trigger) ---
    enable_abs: bool = True
    abs_brake_threshold: int = 80
    abs_min_speed_kmh: float = 15.0
    abs_slip_ratio_threshold: float = 1.0
    abs_combined_slip_threshold: float = 1.0
    abs_freq: int = 35
    abs_amp: int = 10  # MARK: 10 was too weak for the trigger motor to be felt

    # --- Throttle (right trigger): exponential ramp baseline -> full press ---
    # Kept softer than the brake — a real gas pedal has very little resistance
    # compared to a brake pedal, and we need finger-travel budget free for the
    # gear-shift / rev-limit vibration animations.
    # Above 98% throttle uses force 255 inside the same ramp logic.
    enable_throttle_resistance: bool = True
    throttle_baseline_force: int = 0
    throttle_max_force: int = 3    # softer than brake on purpose
    throttle_curve: float = 10.5     # steeper = even softer at light press

    # --- Rev limiter buzz (right trigger) ---
    enable_rev_limiter: bool = True
    rev_limit_ratio: float = 0.92   # MARK: lowered to 0.92 so it kicks in slightly before hard cutoff
    rev_limit_freq: int = 30
    rev_limit_amp: int = 10        # MARK: 10 was too weak to move the motor

    # --- Gear shift thump (right trigger, single vibration burst) ---
    enable_gear_shift: bool = True
    gear_shift_freq: int = 20           # short, noticeable thump
    gear_shift_amp: int = 255
    gear_shift_duration_ms: float = 100.0

    # --- Misc ---
    enable_startup_pulse: bool = True
    startup_pulse_force: int = 150

    # --- Auto-exit when FH5 closes (cross-platform: Windows + Linux/Proton) ---
    exit_on_game_close: bool = True
    game_process_name_contains: tuple = ("forza",)
    game_poll_interval_s: float = 1.0
    # Fallback: if we've received UDP packets and they stop for this long, exit
    # anyway. Catches Task Manager kills and cases where psutil can't see the
    # game process. Long enough to survive pause menus / loading screens.
    telemetry_lost_exit_s: float = 60.0
