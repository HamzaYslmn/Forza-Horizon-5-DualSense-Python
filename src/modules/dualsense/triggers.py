"""DualSense adaptive trigger effects.

  TriggerAnimations — every effect (ABS, gear shift, rev limiter, resistance...).
                      Owns timing state for effects that span frames.
  Trigger           — one trigger's priority chain (config + wall hysteresis).
  Controller        — builds L2 / R2 and produces a frame for each per tick.
"""

import time

# --- Raw mode bytes ---
M_OFF      = 0x05
M_RIGID    = 0x01
M_PULSE    = 0x06
M_FEEDBACK = 0x21  # MultiplePositionFeedback — per-zone static strength
M_PULSE_AB = 0x26  # Pulse_AB — per-zone strength + rhythmic kickback
RAW_MAX = 255


def _clamp(v, hi=RAW_MAX):
    return max(0, min(hi, round(v)))


# --- Effect primitives (raw HID frames) -----------------------------------

def off():
    return (M_OFF, ())

def rigid(force):
    return (M_RIGID, (0, _clamp(force)))

def vibration(freq, amp):
    return (M_PULSE, (_clamp(freq), _clamp(amp)))

def vibration_wall(amp, freq, wall_zones):
    """Pulse_AB: lower zones buzz at `amp` (1-8), top `wall_zones` stay maxed."""
    a = max(1, min(8, int(amp)))
    w = max(1, min(9, int(wall_zones)))
    zones = [a] * (10 - w) + [8] * w
    active = strength = 0
    for i, s in enumerate(zones):
        active |= 1 << i
        strength |= (s - 1) << (3 * i)
    return (M_PULSE_AB, (
        active & 0xFF, (active >> 8) & 0xFF,
        strength & 0xFF, (strength >> 8) & 0xFF, (strength >> 16) & 0xFF, (strength >> 24) & 0xFF,
        _clamp(freq), 0, 0, 0,
    ))

def feedback(zones):
    """MultiplePositionFeedback: 10 per-zone strengths (0-8)."""
    active = force = 0
    for i, s in enumerate(zones[:10]):
        s = max(0, min(8, int(s)))
        if s:
            active |= 1 << i
            force |= (s - 1) << (3 * i)
    return (M_FEEDBACK, (
        active & 0xFF, (active >> 8) & 0xFF,
        force & 0xFF, (force >> 8) & 0xFF, (force >> 16) & 0xFF, (force >> 24) & 0xFF,
        0, 0, 0, 0,
    ))


# --- Helpers --------------------------------------------------------------

def _amp_to_strength(amp_byte):
    return max(1, min(8, (max(0, int(amp_byte)) // 32) + 1))

def _max_slip(t, prefix):
    return max(abs(t.get(f"{prefix}_{w}", 0.0)) for w in ("fl", "fr", "rl", "rr"))

def _ramp(value, deadzone, baseline, max_force, curve, ceiling):
    """deadzone..ceiling -> baseline..max_force, curve = exponent."""
    if value < deadzone:
        return baseline
    r = min(1.0, (value - deadzone) / max(ceiling - deadzone, 1))
    return baseline + (max_force - baseline) * (r ** curve)

def _wall_state(value, engaged, engage_at, release_at):
    """Hysteresis: enter wall at >= engage_at, leave at < release_at."""
    return value >= release_at if engaged else value >= engage_at

def build_wall(zones):
    """Static firmware wall — top `zones` (1-9) maxed. Built once at startup."""
    n = max(1, min(9, int(zones)))
    return feedback([0] * (10 - n) + [8] * n)


# --- Animations -----------------------------------------------------------

class TriggerAnimations:
    """Every trigger effect lives here. Methods return an HID frame or None."""

    def __init__(self):
        self._prev_gear = 0
        self._shift_until = 0.0
        self._rev_until = 0.0

    def arm_shift(self, t, s, now):
        gear, speed = t.get("gear", 0), t.get("speed", 0.0)
        if (self._prev_gear > 0 and gear > 0
                and gear != self._prev_gear and speed > 3.0):
            self._shift_until = now + s.gear_shift_duration_ms / 1000.0
        self._prev_gear = gear

    def shift_burst(self, s, now, pedal, wall_engage_at):
        if now >= self._shift_until:
            return None
        # Wall kickback when pedal is deep past the wall, else plain buzz.
        if pedal >= (wall_engage_at + RAW_MAX) // 2:
            return vibration_wall(_amp_to_strength(s.gear_shift_amp), s.gear_shift_freq, s.wall_zones)
        return vibration(s.gear_shift_freq, s.gear_shift_amp)

    def rev_buzz(self, t, s, now):
        # Brief hold so rpm bouncing against the limit doesn't stutter.
        if not s.enable_rev_limiter:
            return None
        if t.get("accel", 0) >= s.accel_deadzone:
            max_rpm = t.get("max_rpm", 0.0)
            rpm_r = t.get("rpm", 0.0) / max_rpm if max_rpm > 0 else 0.0
            if rpm_r > s.rev_limit_ratio:
                self._rev_until = now + s.rev_limit_hold_ms / 1000.0
        if now < self._rev_until:
            return vibration(s.rev_limit_freq, s.rev_limit_amp)
        return None

    def abs_pulse(self, t, s):
        if not s.enable_abs:
            return None
        if t.get("brake", 0) < s.abs_brake_threshold or t.get("speed", 0.0) < s.abs_min_speed_kmh:
            return None
        if (_max_slip(t, "tire_slip_ratio") < s.abs_slip_ratio_threshold
                and _max_slip(t, "tire_combined_slip") < s.abs_combined_slip_threshold):
            return None
        return vibration(s.abs_freq, s.abs_amp)

    def brake_resistance(self, t, s):
        handbrake = s.enable_handbrake_bonus and t.get("handbrake", 0)
        if not s.enable_brake_resistance:
            return rigid(s.handbrake_bonus) if handbrake else off()
        force = _ramp(t.get("brake", 0), s.brake_deadzone, s.brake_baseline_force,
                      s.brake_max_force, s.brake_curve, s.brake_wall_engage_at)
        if handbrake:
            force += s.handbrake_bonus
        return rigid(force)

    def throttle_ramp(self, t, s):
        if not s.enable_throttle_resistance:
            return off()
        return rigid(_ramp(t.get("accel", 0), s.accel_deadzone, s.throttle_baseline_force,
                           s.throttle_max_force, s.throttle_curve, s.throttle_wall_engage_at))


# --- Controller -----------------------------------------------------------

class Controller:
    """Produces (L2, R2) frames per tick.

    Priority L2: shift thump -> ABS rumble -> wall -> brake resistance.
    Priority R2: shift thump -> rev limiter -> wall -> throttle ramp.
    """

    def __init__(self, settings):
        self.anim = TriggerAnimations()
        self.wall = build_wall(settings.wall_zones)
        self._l2_in_wall = False
        self._r2_in_wall = False

    def update(self, t, s):
        if not t.get("on", False):
            return off(), off()
        now = time.monotonic()
        if s.enable_gear_shift or s.enable_gear_shift_brake:
            self.anim.arm_shift(t, s, now)
        return self.L2(t, s, now), self.R2(t, s, now)

    def L2(self, t, s, now):
        brake = t.get("brake", 0)
        if s.enable_gear_shift_brake:
            shift = self.anim.shift_burst(s, now, brake, s.brake_wall_engage_at)
            if shift:
                return shift
        pulse = self.anim.abs_pulse(t, s)
        if pulse:
            return pulse
        self._l2_in_wall = _wall_state(brake, self._l2_in_wall,
                                       s.brake_wall_engage_at, s.brake_wall_release_at)
        if self._l2_in_wall:
            return self.wall
        return self.anim.brake_resistance(t, s)

    def R2(self, t, s, now):
        accel = t.get("accel", 0)
        if s.enable_gear_shift:
            shift = self.anim.shift_burst(s, now, accel, s.throttle_wall_engage_at)
            if shift:
                return shift
        rev = self.anim.rev_buzz(t, s, now)
        if rev:
            return rev
        self._r2_in_wall = _wall_state(accel, self._r2_in_wall,
                                       s.throttle_wall_engage_at, s.throttle_wall_release_at)
        if self._r2_in_wall:
            return self.wall
        return self.anim.throttle_ramp(t, s)
