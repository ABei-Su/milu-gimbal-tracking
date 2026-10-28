"""Bounded mechanical-zero homing, independent of the camera."""

import math


def home_targets(total, mechanical, max_travel):
    if len(total) != 2 or len(mechanical) != 2:
        raise ValueError("HOME_INVALID_AXES")
    targets = []
    for motor, (angle, single) in enumerate(zip(total, mechanical), 1):
        if not math.isfinite(angle) or not math.isfinite(single) or not 0 <= single < 360:
            raise ValueError("HOME_INVALID_FEEDBACK")
        delta = (180 - single) % 360 - 180
        if abs(delta) > max_travel:
            raise ValueError(
                f"HOME_TRAVEL_EXCEEDED: motor={motor} mechanical={single} "
                f"delta={delta} limit={max_travel}"
            )
        targets.append(angle + delta)
    return tuple(targets)


def approach(current, goal, step):
    return tuple(a + max(-step, min(step, b - a)) for a, b in zip(current, goal))
