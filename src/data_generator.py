"""Reproducible synthetic transaction data.

Everything here is fabricated: users, devices, coordinates, and IP addresses
(drawn only from the RFC 5737 documentation ranges, which are reserved for
examples and never route to real hosts). No real customer or platform data.

The generator produces mostly ordinary behaviour plus a smaller set of
deliberately anomalous scenarios. Each row carries a ``scenario`` label so
results can be inspected by scenario; the risk engine never reads that column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

DEFAULT_SEED = 42
DEFAULT_USERS = 55
WINDOW_DAYS = 45
START = datetime(2026, 3, 2, tzinfo=timezone.utc)

# (city, ISO country, latitude, longitude)
CITIES: dict[str, tuple[str, str, float, float]] = {
    "New York": ("New York", "US", 40.7128, -74.0060),
    "Los Angeles": ("Los Angeles", "US", 34.0522, -118.2437),
    "Chicago": ("Chicago", "US", 41.8781, -87.6298),
    "Houston": ("Houston", "US", 29.7604, -95.3698),
    "Seattle": ("Seattle", "US", 47.6062, -122.3321),
    "Miami": ("Miami", "US", 25.7617, -80.1918),
    "Boston": ("Boston", "US", 42.3601, -71.0589),
    "San Francisco": ("San Francisco", "US", 37.7749, -122.4194),
    "Toronto": ("Toronto", "CA", 43.6532, -79.3832),
    "London": ("London", "GB", 51.5074, -0.1278),
    "Berlin": ("Berlin", "DE", 52.5200, 13.4050),
    "Sydney": ("Sydney", "AU", -33.8688, 151.2093),
    "Tokyo": ("Tokyo", "JP", 35.6762, 139.6503),
    "Singapore": ("Singapore", "SG", 1.3521, 103.8198),
    "Lagos": ("Lagos", "NG", 6.5244, 3.3792),
    "Sao Paulo": ("Sao Paulo", "BR", -23.5505, -46.6333),
}
US_HOMES = [c for c, v in CITIES.items() if v[1] == "US"]
OTHER_HOMES = ["Toronto", "London", "Berlin", "Sydney"]
FAR_CITIES = ["London", "Berlin", "Sydney", "Tokyo", "Singapore", "Lagos", "Sao Paulo"]

NORMAL_MERCHANTS = ["groceries", "restaurants", "retail", "subscriptions", "travel", "utilities", "peer_transfer"]
HIGH_RISK_MERCHANTS = ["crypto_exchange", "gift_cards", "wire_transfer"]

# RFC 5737 documentation-only address blocks (TEST-NET-1/2/3).
IP_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")

_HOUR_WEIGHTS = np.array([0.2] * 6 + [1.0] * 3 + [3.0] * 12 + [1.5] * 3)
_HOUR_PROBS = _HOUR_WEIGHTS / _HOUR_WEIGHTS.sum()


@dataclass
class _User:
    user_id: str
    home_city: str
    devices: list[str]
    home_ips: list[str]
    median_amount: float
    age_at_start: int
    is_traveler: bool = False


@dataclass
class _Builder:
    rng: np.random.Generator
    rows: list[dict] = field(default_factory=list)
    ip_scores: dict[str, float] = field(default_factory=dict)
    _ip_pool: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        pool = [f"{p}{i}" for p in IP_PREFIXES for i in range(1, 255)]
        self._ip_pool = [pool[i] for i in self.rng.permutation(len(pool))]

    def new_ip(self, low: float, high: float) -> str:
        ip = self._ip_pool.pop()
        self.ip_scores[ip] = float(round(self.rng.uniform(low, high), 1))
        return ip

    def add(self, user: _User, ts: datetime, amount: float, device: str, ip: str, city: str,
            merchant: str, failed: int, scenario: str) -> None:
        _, country, lat, lon = CITIES[city]
        jitter = self.rng.normal(0, 0.03, size=2)
        age = user.age_at_start + max(0, (ts - START).days)
        self.rows.append({
            "timestamp": ts,
            "user_id": user.user_id,
            "amount": round(max(1.0, float(amount)), 2),
            "currency": "USD",
            "device_id": device,
            "ip_address": ip,
            "ip_risk_score": self.ip_scores[ip],
            "country": country,
            "city": city,
            "latitude": round(lat + float(jitter[0]), 4),
            "longitude": round(lon + float(jitter[1]), 4),
            "merchant_category": merchant,
            "account_age_days": age,
            "failed_login_attempts": failed,
            "scenario": scenario,
        })


def _random_ts(rng: np.random.Generator, day_low: float, day_high: float) -> datetime:
    day = int(rng.uniform(day_low, day_high))
    hour = int(rng.choice(24, p=_HOUR_PROBS))
    return START + timedelta(days=day, hours=hour, minutes=int(rng.integers(0, 60)), seconds=int(rng.integers(0, 60)))


def _make_users(b: _Builder, n_users: int) -> list[_User]:
    rng = b.rng
    users = []
    for i in range(1, n_users + 1):
        home = str(rng.choice(US_HOMES)) if rng.random() < 0.85 else str(rng.choice(OTHER_HOMES))
        uid = f"U{i:04d}"
        young = rng.random() < 0.10
        users.append(_User(
            user_id=uid,
            home_city=home,
            devices=[f"DEV-{uid}-{k}" for k in range(int(rng.integers(1, 3)))],
            home_ips=[b.new_ip(0, 20) for _ in range(2)],
            median_amount=float(np.clip(rng.lognormal(np.log(45), 0.6), 10, 250)),
            age_at_start=int(rng.integers(1, 25)) if young else int(rng.integers(60, 1500)),
        ))
    return users


def _legit_activity(b: _Builder, users: list[_User]) -> None:
    """Ordinary behaviour, plus a few benign oddities that resemble fraud."""
    rng = b.rng
    for user in users:
        n_txn = 6 + int(rng.integers(2, 8))
        times = sorted(
            [_random_ts(rng, 0, 28) for _ in range(6)] + [_random_ts(rng, 0, WINDOW_DAYS) for _ in range(n_txn - 6)]
        )

        trip_ts = None
        if rng.random() < 0.10:  # a customer travelling abroad
            user.is_traveler = True
            trip_ts = _random_ts(rng, 30, 42)
            times = [t for t in times if abs((t - trip_ts).total_seconds()) > 36 * 3600]

        devices = list(user.devices)
        for idx, ts in enumerate(times):
            scenario, device = "normal", str(rng.choice(devices))
            if idx >= 6 and rng.random() < 0.04:  # bought a new phone
                device = f"DEV-{user.user_id}-N{idx}"
                devices.append(device)
                scenario = "benign_new_device"
            merchant = str(rng.choice(HIGH_RISK_MERCHANTS if rng.random() < 0.03 else NORMAL_MERCHANTS))
            failed = int(rng.choice([0, 1, 2], p=[0.90, 0.08, 0.02]))
            b.add(user, ts, user.median_amount * rng.lognormal(0, 0.5), device,
                  str(rng.choice(user.home_ips)), user.home_city, merchant, failed, scenario)

        if trip_ts is not None:
            home_country = CITIES[user.home_city][1]
            city = str(rng.choice([c for c in FAR_CITIES if CITIES[c][1] != home_country]))
            hotel_ip = b.new_ip(10, 45)
            for k in range(2):
                b.add(user, trip_ts + timedelta(hours=3 * k), user.median_amount * rng.lognormal(0, 0.5),
                      user.devices[0], hotel_ip, city, str(rng.choice(NORMAL_MERCHANTS)), 0, "benign_travel")


def _anomalies(b: _Builder, users: list[_User]) -> None:
    """Deliberately suspicious scenarios injected into the later part of the window."""
    rng = b.rng
    eligible = [u for u in users if not u.is_traveler]

    def pick() -> _User:
        return eligible[int(rng.integers(len(eligible)))]

    def far_city(user: _User) -> str:
        home_country = CITIES[user.home_city][1]
        return str(rng.choice([c for c in FAR_CITIES if CITIES[c][1] != home_country]))

    for n in range(12):  # account takeover: new device + new country + bad IP + big amount
        user, ts = pick(), _random_ts(rng, 30, 44)
        city = far_city(user)
        ip = b.new_ip(72, 98)
        device = f"DEV-ATK-{n:03d}"
        merchant = str(rng.choice(HIGH_RISK_MERCHANTS)) if rng.random() < 0.6 else "retail"
        failed = int(rng.integers(3, 9))
        b.add(user, ts, user.median_amount * rng.uniform(5, 14), device, ip, city, merchant, failed, "account_takeover")
        if rng.random() < 0.3:
            b.add(user, ts + timedelta(minutes=int(rng.integers(2, 7))), user.median_amount * rng.uniform(6, 16),
                  device, ip, city, merchant, failed, "account_takeover")

    for _ in range(8):  # velocity burst / card testing from a proxy-like IP
        user, ts = pick(), _random_ts(rng, 30, 44)
        ip = b.new_ip(50, 85)
        device = user.devices[0]
        merchant = str(rng.choice(["gift_cards", "crypto_exchange", "retail"]))
        for k in range(int(rng.integers(5, 9))):
            ts = ts + timedelta(seconds=int(rng.integers(20, 90)))
            b.add(user, ts, rng.uniform(2, 25), device, ip, user.home_city, merchant,
                  int(rng.integers(0, 2)), "velocity_burst")

    for _ in range(8):  # impossible travel: home transaction, then far away shortly after
        user, ts = pick(), _random_ts(rng, 30, 44)
        b.add(user, ts, user.median_amount * rng.lognormal(0, 0.4), user.devices[0], user.home_ips[0],
              user.home_city, "retail", 0, "normal")
        device = user.devices[0] if rng.random() < 0.5 else f"DEV-TRV-{int(rng.integers(1000, 9999))}"
        b.add(user, ts + timedelta(minutes=int(rng.integers(20, 90))), user.median_amount * rng.uniform(1, 3),
              device, b.new_ip(30, 70), far_city(user), str(rng.choice(NORMAL_MERCHANTS)), 0, "impossible_travel")

    for _ in range(8):  # amount spike from otherwise normal context
        user, ts = pick(), _random_ts(rng, 30, 44)
        merchant = str(rng.choice(HIGH_RISK_MERCHANTS)) if rng.random() < 0.4 else "retail"
        b.add(user, ts, user.median_amount * rng.uniform(8, 18), user.devices[0], user.home_ips[0],
              user.home_city, merchant, 0, "amount_spike")

    for _ in range(6):  # known-bad IP on otherwise normal activity
        user, ts = pick(), _random_ts(rng, 30, 44)
        b.add(user, ts, user.median_amount * rng.lognormal(0, 0.4), user.devices[0], b.new_ip(86, 99),
              user.home_city, str(rng.choice(NORMAL_MERCHANTS)), 0, "ip_anomaly")


def generate_transactions(seed: int = DEFAULT_SEED, n_users: int = DEFAULT_USERS) -> pd.DataFrame:
    """Return a deterministic synthetic transaction table sorted by time."""
    builder = _Builder(rng=np.random.default_rng(seed))
    users = _make_users(builder, n_users)
    _legit_activity(builder, users)
    _anomalies(builder, users)

    df = pd.DataFrame(builder.rows).sort_values(["timestamp", "user_id"], kind="stable").reset_index(drop=True)
    df.insert(0, "transaction_id", [f"TXN-{i:06d}" for i in range(1, len(df) + 1)])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df
