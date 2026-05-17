"""All tunables in one place. Forces 0-255, frequencies in Hz."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    # --- UDP ---
    udp_host: str = "127.0.0.1"
    udp_port: int = 5300
    udp_timeout: float = 0.5

    # --- Shared pedal config ---
    pedal_value_max: int = 255
    wall_zones: int = 2                       # firmware wall depth: 1 = only zone 9 (lightest), 9 = whole travel walled

    # =============================================================
    # L2 — Brake pedal
    # =============================================================

    # Resistance: rigid curve 0..wall_engage_at -> baseline..max_force, firmware wall at 100%.
    enable_brake_resistance: bool = True
    brake_deadzone: int = 50
    brake_baseline_force: int = 10
    brake_max_force: int = 60                 # rigid force at brake_wall_engage_at (peak of the curve before the wall)
    brake_curve: float = 5.0                  # parabolic: light through mid travel, sharply firm near the wall
    brake_wall_engage_at: int = 250           # accel byte to switch to firmware wall
    brake_wall_release_at: int = 200          # accel byte to release the wall back to rigid curve (hysteresis)

    # Handbrake bonus: flat extra force when handbrake is engaged.
    enable_handbrake_bonus: bool = True
    handbrake_bonus: int = 25

    # ABS pulse: vibrate when tire slip telemetry crosses thresholds under hard braking.
    enable_abs: bool = True
    abs_brake_threshold: int = 80
    abs_min_speed_kmh: float = 15.0
    abs_slip_ratio_threshold: float = 1.0
    abs_combined_slip_threshold: float = 1.0
    abs_freq: int = 10
    abs_amp: int = 20

    # =============================================================
    # R2 — Gas pedal
    # =============================================================

    # Resistance: light rigid curve 0..wall_engage_at -> baseline..max_force, firmware wall at 100%.
    enable_throttle_resistance: bool = True
    accel_deadzone: int = 50
    throttle_baseline_force: int = 0
    throttle_max_force: int = 8               # rigid force at the wall threshold — much lighter than the brake
    throttle_curve: float = 5.0               # parabolic: feather-light early, slightly firmer near the wall
    throttle_wall_engage_at: int = 250        # accel byte to switch to firmware wall
    throttle_wall_release_at: int = 200       # accel byte to release the wall back to rigid (hysteresis)

    # Rev limiter: vibrate when rpm/max_rpm exceeds the ratio.
    enable_rev_limiter: bool = True
    rev_limit_ratio: float = 0.93             # fire right at the cutoff, not across the whole upper rpm range
    rev_limit_freq: int = 20
    rev_limit_amp: int = 1                    # raw 0-255 byte for mode 0x06 vibration amplitude
    rev_limit_hold_ms: float = 120.0          # hold buzz this long after each trigger so the rpm bounce doesn't stutter it

    # Gear shift: single short vibration burst on up/downshift while moving.
    enable_gear_shift: bool = True
    enable_gear_shift_brake: bool = True
    gear_shift_freq: int = 20
    gear_shift_amp: int = 255
    gear_shift_duration_ms: float = 100.0

    # =============================================================
    # System
    # =============================================================

    # Startup pulse: brief trigger buzz to confirm HID connection on launch.
    enable_startup_pulse: bool = True
    startup_pulse_force: int = 150



    # Reconnect interval when the controller is missing or disconnects.
    reconnect_interval_s: float = 10.0

    # Auto-exit when game closes (Windows + Linux/Proton). Telemetry-lost is a fallback for Task Manager kills.
    exit_on_game_close: bool = True
    game_process_name_contains: tuple = ("forza",)
    game_poll_interval_s: float = 1.0
    telemetry_lost_exit_s: float = 60.0

    # When True, closing the window hides to the system tray instead of quitting.
    # Auto-disabled if the tray can't initialize (typically Linux without an
    # AppIndicator-compatible status notifier).
    minimize_to_tray: bool = True
