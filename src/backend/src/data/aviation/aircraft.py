"""Aviation Reference Master / `aircraft_registry` — synthetic aircraft tails.

Each aircraft has a tail number, ICAO 24-bit address, type, operator, fleet age,
and cabin config. Tail-number formats follow country prefix conventions
(N-numbers for US, G-XXXX for UK, VH-XXX for Australia, etc.).
"""
from __future__ import annotations

import random
import string

import polars as pl

# Aircraft type catalog — (icao, iata, manufacturer, model, mtow_kg, typical seats range)
_AIRCRAFT_TYPES = [
    ("B737", "737", "Boeing", "737-800", 79016, (150, 189)),
    ("B738", "738", "Boeing", "737-800", 79016, (160, 189)),
    ("B739", "739", "Boeing", "737-900", 85139, (180, 220)),
    ("B38M", "7M8", "Boeing", "737 MAX 8", 82190, (162, 210)),
    ("B39M", "7M9", "Boeing", "737 MAX 9", 88314, (178, 220)),
    ("B752", "752", "Boeing", "757-200", 115680, (180, 239)),
    ("B763", "763", "Boeing", "767-300", 186880, (218, 351)),
    ("B772", "772", "Boeing", "777-200", 247200, (305, 440)),
    ("B77W", "77W", "Boeing", "777-300ER", 351530, (350, 396)),
    ("B788", "788", "Boeing", "787-8", 227930, (242, 359)),
    ("B789", "789", "Boeing", "787-9", 254011, (290, 406)),
    ("B78X", "78J", "Boeing", "787-10", 254011, (318, 440)),
    ("B748", "74H", "Boeing", "747-8", 447696, (410, 605)),
    ("A319", "319", "Airbus", "A319", 75500, (124, 156)),
    ("A320", "320", "Airbus", "A320", 78000, (150, 186)),
    ("A21N", "32Q", "Airbus", "A321neo", 97000, (180, 244)),
    ("A20N", "32N", "Airbus", "A320neo", 79000, (150, 194)),
    ("A21", "321", "Airbus", "A321", 93500, (170, 220)),
    ("A332", "332", "Airbus", "A330-200", 230000, (246, 380)),
    ("A333", "333", "Airbus", "A330-300", 242000, (277, 440)),
    ("A339", "339", "Airbus", "A330-900neo", 251000, (260, 460)),
    ("A359", "359", "Airbus", "A350-900", 280000, (300, 440)),
    ("A35K", "351", "Airbus", "A350-1000", 319000, (350, 480)),
    ("A388", "388", "Airbus", "A380-800", 575000, (469, 853)),
    ("E190", "E90", "Embraer", "E190", 51800, (96, 114)),
    ("E195", "E95", "Embraer", "E195", 52290, (108, 132)),
    ("E75L", "E7W", "Embraer", "E175", 38790, (76, 88)),
    ("CRJ9", "CR9", "Bombardier", "CRJ900", 38330, (76, 90)),
    ("AT72", "AT7", "ATR", "ATR 72", 23000, (66, 78)),
]

# Country prefix → tail-number generator pattern
def _tail_number(country_iso: str, rng: random.Random) -> str:
    if country_iso == "US":
        digits = rng.randint(1, 5)
        suffix_len = rng.choice([0, 1, 2])
        body = "".join(str(rng.randint(0, 9)) for _ in range(digits))
        # US N-numbers: no I or O
        valid = [c for c in string.ascii_uppercase if c not in "IO"]
        suffix = "".join(rng.choice(valid) for _ in range(suffix_len))
        # Avoid leading zero
        if body.startswith("0"):
            body = str(rng.randint(1, 9)) + body[1:]
        return f"N{body}{suffix}"
    if country_iso == "GB":
        return "G-" + "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    if country_iso == "DE":
        return "D-A" + "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    if country_iso == "FR":
        return "F-" + "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    if country_iso == "JP":
        return f"JA{rng.randint(100, 999)}{rng.choice(string.ascii_uppercase)}"
    if country_iso == "AU":
        return "VH-" + "".join(rng.choice(string.ascii_uppercase) for _ in range(3))
    if country_iso == "CA":
        return "C-" + "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    if country_iso == "AE":
        return f"A6-{''.join(rng.choice(string.ascii_uppercase) for _ in range(3))}"
    if country_iso == "QA":
        return f"A7-{''.join(rng.choice(string.ascii_uppercase) for _ in range(3))}"
    if country_iso == "SG":
        return f"9V-{''.join(rng.choice(string.ascii_uppercase) for _ in range(3))}"
    if country_iso == "IN":
        return f"VT-{''.join(rng.choice(string.ascii_uppercase) for _ in range(3))}"
    if country_iso == "BR":
        return f"PR-{''.join(rng.choice(string.ascii_uppercase) for _ in range(3))}"
    # Fallback — invent a plausible format
    return f"{country_iso[:2]}-{''.join(rng.choice(string.ascii_uppercase) for _ in range(4))}"


def _icao24(rng: random.Random) -> str:
    return f"{rng.randint(0, 0xFFFFFF):06X}"


def build_aircraft_registry(
    airlines: pl.DataFrame,
    n_aircraft: int = 250,
    seed: int = 42,
    current_year: int = 2026,
) -> pl.DataFrame:
    """Generate a synthetic aircraft registry.

    Each row represents one aircraft tail, owned by an airline (or a few cargo/lessor ops),
    with type, age, MTOW, and cabin configuration.
    """
    rng = random.Random(seed)
    airline_iatas = airlines["iata"].to_list()
    airline_countries = dict(zip(airlines["iata"].to_list(), airlines["country_iso"].to_list()))
    statuses = ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE", "STORED", "LEASED_OUT"]

    rows = []
    used_icao24 = set()
    used_tails = set()

    for _ in range(n_aircraft):
        airline_iata = rng.choice(airline_iatas)
        country = airline_countries[airline_iata]
        ac_type = rng.choice(_AIRCRAFT_TYPES)
        ac_icao, ac_iata, mfg, model, mtow_kg, seat_range = ac_type

        # Unique tail number
        while True:
            tail = _tail_number(country, rng)
            if tail not in used_tails:
                used_tails.add(tail)
                break

        # Unique ICAO 24-bit
        while True:
            icao24 = _icao24(rng)
            if icao24 not in used_icao24:
                used_icao24.add(icao24)
                break

        year_manufactured = rng.randint(current_year - 25, current_year - 1)

        # Plausible cabin config
        total_seats = rng.randint(*seat_range)
        if mtow_kg > 200000:  # widebody
            first = rng.choice([0, 8, 12, 14])
            business = rng.choice([28, 42, 48, 64])
        elif mtow_kg > 80000:  # mid
            first = rng.choice([0, 0, 8])
            business = rng.choice([12, 16, 20, 24])
        else:
            first = 0
            business = rng.choice([0, 8, 12, 16])
        economy = max(total_seats - first - business, 50)

        rows.append({
            "tail_number": tail,
            "icao24": icao24,
            "aircraft_type_icao": ac_icao,
            "aircraft_type_iata": ac_iata,
            "manufacturer": mfg,
            "model": model,
            "year_manufactured": year_manufactured,
            "registration_country": country,
            "airline_operator_iata": airline_iata,
            "mtow_kg": mtow_kg,
            "seat_economy": economy,
            "seat_business": business,
            "seat_first": first,
            "active_status": rng.choice(statuses),
        })

    return pl.DataFrame(rows)
