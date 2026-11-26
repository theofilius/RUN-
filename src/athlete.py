"""The runner the analysis is for: the settings that differ from person to person.

config.py holds the first runner's values (tee). Switching to another runner calls
use() with their values; the analysis reads ATHLETE when it runs, not when it is
imported, so the switch reaches every module. Values derived from these (the planner's
heart-rate zones) register with on_change() and are recalculated on a switch.

One runner at a time: the dashboard is a local, single-person app.
"""

import math
from dataclasses import dataclass, field

from src import config

CONFIRM_BPM = 2       # own rule: a max HR counts once another run came within 2 bpm of it
PLAUSIBLE_MAX = 230   # own rule: a higher reading is a sensor error, not a heart rate


@dataclass
class Athlete:
    name: str = "tee"
    max_hr: int = config.MAX_HR
    max_hr_source: str = "runs"          # "runs" (highest seen), "entered" or "age" (Tanaka 2001)
    easy_hr_fraction: float = config.EASY_HR_FRACTION
    injured_last_12_months: bool = config.INJURED_LAST_12_MONTHS
    start_runs_per_week: int = config.START_RUNS_PER_WEEK
    races: dict = field(default_factory=lambda: dict(config.RACES))
    talk_test_hr: int | None = None      # HR at the last stage you could still speak comfortably (Persinger 2004)

    @property
    def easy_hr_max(self):
        """Top of easy: your talk test when you did one, otherwise a share of max HR."""
        if self.talk_test_hr:
            return int(self.talk_test_hr)
        return round(self.easy_hr_fraction * self.max_hr)   # whole bpm, like the watch shows


def max_hr_from_runs(max_hrs, within=CONFIRM_BPM):
    """The highest max HR in the runs that another run confirms, or None.

    Confirmed = the next highest run is within `within` bpm. A wrist sensor can lock
    onto cadence and show one high number, but two runs on different days near the same
    peak are hard to fake. Example: 201, 200, 199, 199 gives 201; 210, 201, 200 gives 201.
    """
    values = sorted((int(v) for v in max_hrs
                     if v is not None and not (isinstance(v, float) and math.isnan(v)) and 0 < v <= PLAUSIBLE_MAX),
                    reverse=True)
    for high, next_high in zip(values, values[1:]):
        if next_high >= high - within:
            return high
    return None


ATHLETE = Athlete()
_listeners = []


def on_change(listener):
    """Call listener() now and after every switch of runner."""
    _listeners.append(listener)
    listener()


def use(athlete):
    """Make `athlete` the runner every module reads (in place, so all imports see it)."""
    for name, value in vars(athlete).items():
        setattr(ATHLETE, name, value)
    for listener in _listeners:
        listener()
