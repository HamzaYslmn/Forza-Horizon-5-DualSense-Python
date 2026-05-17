"""User-facing labels, help text, and section grouping for the GUI.

Lives separately from `Settings` so the dataclass stays a clean source of
truth for tunable values without being polluted by display strings. Every
help string is written to answer three questions:

  1. What does this control do to your DualSense?
  2. What happens if you turn it up (or on)?
  3. What happens if you turn it down (or off)?

The import-time `_validate_against_settings()` raises immediately if a spec
points at a `Settings` field that doesn't exist, so a rename in `settings.py`
or `labels.py` fails loudly on the next launch.
"""
from __future__ import annotations

from dataclasses import dataclass

from modules.settings import Settings


@dataclass(frozen=True)
class FieldSpec:
    """A numeric Settings field rendered as an entry on the Settings tab."""
    attr: str
    label: str
    help: str
    lo: float
    hi: float


@dataclass(frozen=True)
class ToggleSpec:
    """A boolean Settings field rendered as a switch on the Controls tab."""
    attr: str
    label: str
    help: str


# ---- Controls tab (boolean switches) -------------------------------------
# Brake (L2) and Throttle (R2) columns of effect switches, plus a Window
# column for app-wide behavior (tray, etc).
TOGGLE_GROUPS: list[tuple[str, list[ToggleSpec]]] = [
    ("Brake (L2)", [
        ToggleSpec(
            "enable_brake_resistance", "Brake stiffness",
            "Pushes back on the L2 trigger as you press it harder, like a real brake pedal.\n\n"
            "• ON: L2 feels heavier the deeper you press — the core 'brake pedal' immersion.\n"
            "• OFF: L2 has no resistance, feels like a normal gaming trigger.\n\n"
            "Tune the feel with 'Baseline stiffness', 'Max stiffness at the wall', and 'Curve shape'.\n\n"
            "(field: enable_brake_resistance)"
        ),
        ToggleSpec(
            "enable_handbrake_bonus", "Handbrake extra stiffness",
            "While the handbrake is engaged, adds extra resistance on top of the normal brake feel.\n\n"
            "• ON: L2 feels noticeably stiffer during drifts/handbrake turns — easy to distinguish.\n"
            "• OFF: handbrake feels identical to a normal brake press.\n\n"
            "Amount of the bonus is set by 'Handbrake bonus stiffness' below.\n\n"
            "(field: enable_handbrake_bonus)"
        ),
        ToggleSpec(
            "enable_abs", "ABS rumble",
            "Buzzes the L2 trigger when the tires slip under hard braking — like feeling ABS pulse through a real brake pedal.\n\n"
            "• ON: you feel a rapid pulse when wheels lock, giving immediate tactile feedback that you're braking too hard.\n"
            "• OFF: no slip feedback through L2.\n\n"
            "Sensitivity tunes via the ABS section on the Settings tab.\n\n"
            "(field: enable_abs)"
        ),
        ToggleSpec(
            "enable_gear_shift_brake", "Shift thump on brake",
            "Brief vibration through L2 on every gear change while moving.\n\n"
            "• ON: feel each shift through the brake trigger too.\n"
            "• OFF: shift feedback only on R2 (if 'Shift thump on throttle' is on).\n\n"
            "(field: enable_gear_shift_brake)"
        ),
    ]),
    ("Throttle (R2)", [
        ToggleSpec(
            "enable_throttle_resistance", "Throttle stiffness",
            "Soft, progressive resistance on R2 as you press it — gives the throttle a sense of weight.\n\n"
            "• ON: R2 has subtle build-up, then a firmer wall at full throttle.\n"
            "• OFF: R2 has no resistance.\n\n"
            "Keep this much lighter than brake stiffness for natural throttle feel.\n\n"
            "(field: enable_throttle_resistance)"
        ),
        ToggleSpec(
            "enable_rev_limiter", "Redline buzz",
            "Buzzes R2 when RPM approaches the rev limiter — a tactile warning before you hit cutoff.\n\n"
            "• ON: feel a buzz right at redline so you know to upshift without looking.\n"
            "• OFF: no rev warning through R2.\n\n"
            "Trigger point set by 'Trigger at RPM ratio' (e.g. 0.93 = at 93% of redline).\n\n"
            "(field: enable_rev_limiter)"
        ),
        ToggleSpec(
            "enable_gear_shift", "Shift thump on throttle",
            "Brief vibration through R2 on every gear change while moving.\n\n"
            "• ON: feel each shift through the throttle trigger.\n"
            "• OFF: no shift feedback on R2 (L2 still gets it if 'Shift thump on brake' is on).\n\n"
            "(field: enable_gear_shift)"
        ),
    ]),
    ("Window", [
        ToggleSpec(
            "minimize_to_tray", "Minimize to tray on close",
            "Controls what the window's X button does.\n\n"
            "• ON: clicking X hides the window to a tray icon. The app stays running, your triggers keep working, and you re-open from the tray.\n"
            "• OFF: clicking X quits the app entirely.\n\n"
            "Auto-disabled if the tray can't initialize on your desktop. The 'Quit' button at the bottom-right always quits regardless of this setting.\n\n"
            "(field: minimize_to_tray)"
        ),
    ]),
]


# ---- Settings tab (numeric entries) --------------------------------------
SECTIONS: list[tuple[str, list[FieldSpec]]] = [
    ("Pedals / deadzones", [
        FieldSpec(
            "accel_deadzone", "Throttle deadzone",
            "Ignore R2 presses below this raw 0-255 byte value.\n\n"
            "• Higher: tolerates trigger stick or rattle at rest — but reduces sensitivity to light throttle inputs.\n"
            "• Lower: every micro-movement reads as throttle input.\n"
            "• 0: no deadzone at all.\n\n"
            "Default 50 (~20%) is a safe middle ground.\n\n"
            "(field: accel_deadzone)",
            0, 255,
        ),
        FieldSpec(
            "brake_deadzone", "Brake deadzone",
            "Ignore L2 presses below this raw 0-255 byte value.\n\n"
            "• Higher: tolerates trigger stick or rattle at rest — but reduces sensitivity to light brake taps.\n"
            "• Lower: brake responds to even tiny presses.\n"
            "• 0: no deadzone at all.\n\n"
            "Default 50 (~20%) is a safe middle ground.\n\n"
            "(field: brake_deadzone)",
            0, 255,
        ),
    ]),
    ("Brake (L2)", [
        FieldSpec(
            "brake_baseline_force", "Baseline stiffness",
            "Constant resistance applied across the entire brake travel, BEFORE the curve adds extra force.\n\n"
            "• Higher: even a feather-light brake press feels stiff — gives the trigger 'weight' all the way through.\n"
            "• Lower: starts very soft and builds resistance only through the curve.\n"
            "• 0: trigger is free until the curve kicks in.\n\n"
            "(field: brake_baseline_force)",
            0, 255,
        ),
        FieldSpec(
            "brake_max_force", "Max stiffness at the wall",
            "Peak resistance reached right before the firmware 'hard stop' (the wall) engages.\n\n"
            "• Higher: full brake press feels firm — closer to a real brake pedal under load.\n"
            "• Lower: brake stays soft throughout — easier to modulate but less immersive.\n"
            "• 0: no extra resistance on top of the baseline.\n\n"
            "(field: brake_max_force)",
            0, 255,
        ),
        FieldSpec(
            "brake_curve", "Curve shape",
            "Parabolic exponent for how baseline ramps up to max stiffness.\n\n"
            "• Higher (e.g. 8-15): feathery for most of the press, then SUDDENLY firm near the end — dramatic 'brake-by-wire' feel.\n"
            "• Lower (e.g. 1.5-2): near-linear ramp — predictable, smooth, easy to modulate.\n"
            "• Default 5: noticeable progressive feel without being grabby.\n\n"
            "(field: brake_curve)",
            0.1, 20.0,
        ),
        FieldSpec(
            "brake_wall_engage_at", "Wall engages at",
            "Trigger byte at which the firmware's full 'hard stop' kicks in.\n\n"
            "• Lower: hard stop arrives earlier — feels like the brake is at its limit sooner, but you lose useable travel.\n"
            "• Higher: more useable travel before hitting the wall.\n"
            "• 255: wall never engages — only rigid resistance applies.\n\n"
            "(field: brake_wall_engage_at)",
            0, 255,
        ),
        FieldSpec(
            "brake_wall_release_at", "Wall releases at",
            "Hysteresis: trigger byte at which the wall releases back to the rigid curve as you let off the brake.\n\n"
            "Should be LESS than 'Wall engages at' to prevent flutter.\n\n"
            "• Higher (closer to engage): wall releases quickly as you let off — less 'sticky'.\n"
            "• Lower: wall holds longer — more 'sticky' resistance as you ease off.\n\n"
            "(field: brake_wall_release_at)",
            0, 255,
        ),
        FieldSpec(
            "handbrake_bonus", "Handbrake bonus stiffness",
            "Extra flat force added on top of brake stiffness while the handbrake is engaged.\n\n"
            "• Higher: handbrake feels much firmer than regular brake — easy to tell apart.\n"
            "• Lower: subtle difference.\n"
            "• 0: handbrake feels identical to brake.\n\n"
            "Only used when 'Handbrake extra stiffness' is ON.\n\n"
            "(field: handbrake_bonus)",
            0, 255,
        ),
    ]),
    ("Throttle (R2)", [
        FieldSpec(
            "throttle_baseline_force", "Baseline stiffness",
            "Constant resistance across throttle travel, BEFORE the curve adds extra.\n\n"
            "• Higher: throttle has weight from the start.\n"
            "• Lower: throttle is featherlight until the curve engages.\n"
            "• 0 (default): pure featherlight feel — recommended for most cars.\n\n"
            "(field: throttle_baseline_force)",
            0, 255,
        ),
        FieldSpec(
            "throttle_max_force", "Max stiffness at the wall",
            "Peak throttle resistance right before the firmware wall.\n\n"
            "• Higher: throttle feels firm at full press — pronounced 'engine pushing back' sensation.\n"
            "• Lower: stays light throughout.\n"
            "• 0: no extra resistance.\n\n"
            "Keep much lower than brake max force (default 8) — a real throttle pedal is much lighter than a brake.\n\n"
            "(field: throttle_max_force)",
            0, 255,
        ),
        FieldSpec(
            "throttle_curve", "Curve shape",
            "Parabolic exponent for throttle resistance ramp.\n\n"
            "• Higher: feathery early, firm at the end.\n"
            "• Lower: linear ramp.\n"
            "• Default 5: progressive without being grabby.\n\n"
            "(field: throttle_curve)",
            0.1, 20.0,
        ),
        FieldSpec(
            "throttle_wall_engage_at", "Wall engages at",
            "Trigger byte at which the firmware hard-stop kicks in for throttle.\n\n"
            "• Lower: hard stop arrives earlier in the press.\n"
            "• Higher: more useable travel.\n\n"
            "(field: throttle_wall_engage_at)",
            0, 255,
        ),
        FieldSpec(
            "throttle_wall_release_at", "Wall releases at",
            "Hysteresis: trigger byte at which the wall releases as you ease off the throttle.\n\n"
            "Should be LESS than 'Wall engages at'.\n\n"
            "(field: throttle_wall_release_at)",
            0, 255,
        ),
    ]),
    ("ABS rumble", [
        FieldSpec(
            "abs_brake_threshold", "Brake threshold",
            "Minimum brake amount (0-255) before ABS rumble is allowed to fire.\n\n"
            "• Higher: ABS only triggers under heavy braking — more realistic.\n"
            "• Lower: ABS triggers even on light brakes — easier to feel but less authentic.\n\n"
            "(field: abs_brake_threshold)",
            0, 255,
        ),
        FieldSpec(
            "abs_min_speed_kmh", "Min speed (km/h)",
            "Minimum car speed before ABS rumble is allowed.\n\n"
            "• Higher: avoids false triggers from low-speed maneuvering.\n"
            "• Lower: ABS fires even at parking speeds.\n\n"
            "(field: abs_min_speed_kmh)",
            0.0, 500.0,
        ),
        FieldSpec(
            "abs_slip_ratio_threshold", "Slip ratio threshold",
            "Tire slip ratio at which ABS rumble fires.\n\n"
            "• Higher: only buzz when wheels are obviously locking up.\n"
            "• Lower: buzz on subtle slip too — very sensitive feedback.\n\n"
            "(field: abs_slip_ratio_threshold)",
            0.0, 10.0,
        ),
        FieldSpec(
            "abs_combined_slip_threshold", "Combined slip threshold",
            "Combined longitudinal + lateral slip threshold for ABS rumble.\n\n"
            "Same shape as slip-ratio threshold but accounts for braking-while-turning.\n\n"
            "(field: abs_combined_slip_threshold)",
            0.0, 10.0,
        ),
        FieldSpec(
            "abs_freq", "Frequency (Hz)",
            "ABS rumble frequency.\n\n"
            "• Higher: faster, tighter, almost-continuous buzz.\n"
            "• Lower: slow distinct thumping — feels more like classic ABS pulsing.\n\n"
            "(field: abs_freq)",
            0, 255,
        ),
        FieldSpec(
            "abs_amp", "Amplitude",
            "ABS rumble strength (0-255).\n\n"
            "• Higher: stronger, more attention-grabbing.\n"
            "• Lower: subtle — easy to ignore but still present.\n\n"
            "(field: abs_amp)",
            0, 255,
        ),
    ]),
    ("Rev limiter", [
        FieldSpec(
            "rev_limit_ratio", "Trigger at RPM ratio",
            "Fraction of max RPM at which the rev-limit buzz fires.\n\n"
            "• 0.93 (default): fires right at the cutoff.\n"
            "• Closer to 1.0: only buzz right at redline — minimal warning.\n"
            "• Lower (e.g. 0.85): buzz starts earlier — gives you more headroom to upshift.\n\n"
            "Tune per car: different cars hit redline at different ratios.\n\n"
            "(field: rev_limit_ratio)",
            0.0, 1.0,
        ),
        FieldSpec(
            "rev_limit_freq", "Frequency (Hz)",
            "Rev-limit buzz frequency.\n\n"
            "• Higher: tighter, almost continuous warning buzz.\n"
            "• Lower: distinct pulses.\n\n"
            "(field: rev_limit_freq)",
            0, 255,
        ),
        FieldSpec(
            "rev_limit_amp", "Amplitude",
            "Rev-limit buzz strength (0-255).\n\n"
            "• Higher: louder, more urgent warning.\n"
            "• Lower: subtle — barely there.\n\n"
            "(field: rev_limit_amp)",
            0, 255,
        ),
        FieldSpec(
            "rev_limit_hold_ms", "Hold (ms)",
            "Keep buzzing this long after each rev-limit hit so the RPM bounce doesn't stutter the effect.\n\n"
            "• Higher: continuous buzz across the bounce — feels like one sustained warning.\n"
            "• Lower: stutters with the RPM bounce — twitchy.\n\n"
            "(field: rev_limit_hold_ms)",
            0.0, 1000.0,
        ),
    ]),
    ("Gear shift thump", [
        FieldSpec(
            "gear_shift_freq", "Frequency (Hz)",
            "Frequency of the shift thump.\n\n"
            "• Higher: snappy, sharp thump.\n"
            "• Lower: fatter, bassier thump.\n\n"
            "(field: gear_shift_freq)",
            0, 255,
        ),
        FieldSpec(
            "gear_shift_amp", "Amplitude",
            "Thump strength (0-255).\n\n"
            "• Higher: harder, more punctuated.\n"
            "• Lower: gentler reminder.\n\n"
            "(field: gear_shift_amp)",
            0, 255,
        ),
        FieldSpec(
            "gear_shift_duration_ms", "Duration (ms)",
            "Length of the shift thump.\n\n"
            "• Higher: lingering thump — good for slow auto-transmission shifts.\n"
            "• Lower: quick crack — good for sequential / paddle shifters.\n\n"
            "(field: gear_shift_duration_ms)",
            0.0, 2000.0,
        ),
    ]),
    ("Startup / reconnect", [
        FieldSpec(
            "startup_pulse_force", "Startup pulse strength",
            "Brief trigger pulse fired on launch to confirm the HID connection is working.\n\n"
            "• Higher: stronger 'I'm alive' pulse on both triggers.\n"
            "• Lower: subtler.\n"
            "• 0: no pulse — you won't know if HID is alive until the first telemetry packet.\n\n"
            "(field: startup_pulse_force)",
            0, 255,
        ),
        FieldSpec(
            "reconnect_interval_s", "Reconnect interval (s)",
            "How often to retry HID connection if the controller is missing or disconnects.\n\n"
            "• Higher: less HID polling traffic when the controller is off.\n"
            "• Lower: faster reconnect when you turn the controller on.\n"
            "• Default 10s: balanced.\n\n"
            "(field: reconnect_interval_s)",
            0.1, 60.0,
        ),
    ]),
]


# ---- Derived lookups -----------------------------------------------------
FIELD_RANGES: dict[str, tuple[float, float]] = {
    spec.attr: (spec.lo, spec.hi) for _, fields in SECTIONS for spec in fields
}


def format_range(lo: float, hi: float) -> str:
    if isinstance(lo, int) and isinstance(hi, int):
        return f"{lo}-{hi}"
    return f"{lo:g}-{hi:g}"


STARTUP_HINT = (
    "Waiting for Forza Horizon telemetry — in game: "
    "Settings → HUD & Gameplay → Data Out: ON, IP {host}, Port {port}"
)


# ---- Import-time validation ---------------------------------------------
def _validate_against_settings() -> None:
    s = Settings()
    for _, fields in SECTIONS:
        for field_spec in fields:
            if not hasattr(s, field_spec.attr):
                raise AttributeError(
                    f"labels.SECTIONS references nonexistent Settings.{field_spec.attr}"
                )
    for _, toggles in TOGGLE_GROUPS:
        for toggle_spec in toggles:
            if not hasattr(s, toggle_spec.attr):
                raise AttributeError(
                    f"labels.TOGGLE_GROUPS references nonexistent Settings.{toggle_spec.attr}"
                )
            v = getattr(s, toggle_spec.attr)
            if not isinstance(v, bool):
                raise TypeError(
                    f"labels.TOGGLE_GROUPS.{toggle_spec.attr} must be a bool field on Settings, "
                    f"got {type(v).__name__}"
                )


_validate_against_settings()
