"""Runners who use the dashboard, kept in data/users.json.

The first runner, tee, is the one whose data was already in data/ (Garmin sync, CSV
exports, programs): their folder stays data/ itself and their settings are config.py.
A new runner gets data/users/<id>/ and starts from the stats they enter (STAT_FIELDS,
turned into a run history by loaders/manual_stats.py). No password for now: this is a
local app on your own computer.

Online (src/cloud.py) every runner needs a password. Only a salted scrypt hash is
kept. After logging in, the address carries a signed token (login_token) for
TOKEN_DAYS, because every link in the app loads a new page.

  python -m src.users password <id>    set or change a runner's password
"""

import hashlib
import hmac
import json
import re
import secrets
import sys
import time
from datetime import date
from getpass import getpass
from pathlib import Path

from src.athlete import Athlete
from src.config import RUNS_PER_WEEK
from src.env import env_value

SECRET_FILE = ".app_secret"     # signs login tokens; APP_SECRET in the environment wins
TOKEN_DAYS = 30
MIN_PASSWORD = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

USERS_FILE = "users.json"
USERS_DIR = "users"
FIRST_USER = {"id": "tee", "name": "tee", "folder": "", "source": "data"}

# Top of easy effort as a share of max HR, by sex: recreational runners' first threshold
# was at 78.9% (men) / 83.6% (women) of max HR (Nuuttila 2025), and 74.6% / 77.9% in the
# least-trained (Benitez-Munoz 2025). Each value sits between the two, nearer Nuuttila,
# as config.EASY_HR_FRACTION does for men.
EASY_HR_FRACTION_BY_SEX = {"male": 0.78, "female": 0.82}

# What a new runner enters, and why the planner needs it.
STAT_FIELDS = {
    "sex": "sets the easy heart-rate limit (Nuuttila 2025, Benitez-Munoz 2025)",
    "age": "estimates max HR when you do not know it (208 - 0.7 x age, Tanaka 2001)",
    "max_hr": "every heart-rate zone is a share of it; a measured value beats the formula",
    "runs_per_week": "the plan starts at this frequency and adds a run a week",
    "weekly_km": "your recent load: the plan grows from it, at most +30% in 2 weeks (Nielsen 2014)",
    "longest_km": "the long run starts here and grows 1 km a week",
    "easy_pace_s": "with easy HR: your efficiency, which turns every heart rate into a pace",
    "easy_hr": "with easy pace: your efficiency",
    "race": "a recent race or time trial: the estimate for any target distance (Riegel)",
    "injured": "an injury in the last 12 months was the strongest injury predictor (Fokkema 2020)",
}


def load(data_root):
    """{"users": [...]}; tee is always there."""
    path = Path(data_root) / USERS_FILE
    return json.loads(path.read_text()) if path.exists() else {"users": [dict(FIRST_USER)]}


def save(data_root, store):
    path = Path(data_root) / USERS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2))


def find(store, user_id):
    return next((u for u in store["users"] if u["id"] == user_id), None)


def data_dir(data_root, user):
    """The runner's own folder: programs, frozen weeks and activity files go here."""
    return Path(data_root) / user["folder"] if user["folder"] else Path(data_root)


def new_user(store, name, stats, today=None):
    """A runner from entered stats, with an id made from the name (unique in store)."""
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "runner"
    user_id, n = base, 2
    while find(store, user_id):
        user_id, n = f"{base}-{n}", n + 1
    return {"id": user_id, "name": name.strip(), "folder": f"{USERS_DIR}/{user_id}", "source": "stats",
            "stats": {**stats, "as_of": str(today or date.today())}}


def add(data_root, store, user):
    store["users"].append(user)
    save(data_root, store)
    data_dir(data_root, user).mkdir(parents=True, exist_ok=True)


def max_hr(stats):
    """(max HR, source): the entered value, or 208 - 0.7 x age (Tanaka 2001)."""
    if stats.get("max_hr"):
        return int(stats["max_hr"]), "entered"
    return round(208 - 0.7 * stats["age"]), "age"


def has_password(user):
    return bool(user.get("password"))


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT).hex()
    return {"salt": salt, "hash": digest}


def check_password(user, password):
    if not has_password(user):
        return False
    expected = hash_password(password, user["password"]["salt"])["hash"]
    return hmac.compare_digest(expected, user["password"]["hash"])


def set_password(data_root, store, user_id, password):
    find(store, user_id)["password"] = hash_password(password)
    save(data_root, store)


def app_secret(data_root, root=None):
    """The key that signs login tokens: APP_SECRET, else one made once and kept in data/."""
    if value := env_value("APP_SECRET", root or Path(data_root).parent):
        return value
    path = Path(data_root) / SECRET_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


def _signature(user, expires, secret):
    # the password's salt is signed too, so a new password ends every old login
    message = f"{user['id']}|{expires}|{user['password']['salt']}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def login_token(user, secret, now=None):
    expires = int((now or time.time()) + TOKEN_DAYS * 86400)
    return f"{expires}.{_signature(user, expires, secret)}"


def valid_token(user, token, secret, now=None):
    if not (has_password(user) and token and "." in token):
        return False
    expires, signature = token.split(".", 1)
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False
    return hmac.compare_digest(signature, _signature(user, int(expires), secret))


def talk_test_hr(user):
    """The easy limit from the runner's talk test, or None (see set_talk_test)."""
    return (user.get("talk_test") or {}).get("hr")


def set_talk_test(data_root, store, user_id, hr, day=None):
    """Save a talk test result (hr=None removes it, back to the share of max HR)."""
    user = find(store, user_id)
    if hr:
        user["talk_test"] = {"hr": int(hr), "date": str(day or date.today())}
    else:
        user.pop("talk_test", None)
    save(data_root, store)


def athlete(user):
    """The runner's settings: config.py for tee, otherwise from their stats; a talk test for both."""
    if user.get("source") != "stats":
        return Athlete(name=user["name"], talk_test_hr=talk_test_hr(user))
    stats = user["stats"]
    hr, hr_source = max_hr(stats)
    return Athlete(name=user["name"], max_hr=hr, max_hr_source=hr_source,
                   easy_hr_fraction=EASY_HR_FRACTION_BY_SEX[stats["sex"]],
                   injured_last_12_months=bool(stats.get("injured")),
                   start_runs_per_week=max(2, min(RUNS_PER_WEEK, int(stats["runs_per_week"]))),
                   races={}, talk_test_hr=talk_test_hr(user))


def main(argv):
    root = Path(__file__).resolve().parent.parent / "data"
    if len(argv) != 3 or argv[1] != "password":
        sys.exit("python -m src.users password <id>")
    store = load(root)
    if not find(store, argv[2]):
        sys.exit(f"No runner {argv[2]!r}. Runners: {', '.join(u['id'] for u in store['users'])}")
    password = getpass(f"New password for {argv[2]}: ")
    if len(password) < MIN_PASSWORD:
        sys.exit(f"Use at least {MIN_PASSWORD} characters.")
    if getpass("Again: ") != password:
        sys.exit("The two passwords differ.")
    set_password(root, store, argv[2], password)
    print(f"Password set for {argv[2]}.")


if __name__ == "__main__":
    main(sys.argv)
