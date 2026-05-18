"""Aviation Reference Master / `airlines` — major commercial airlines."""
from __future__ import annotations

import polars as pl

# (iata, icao, name, country_iso, alliance)
_AIRLINES = [
    # North America
    ("AA", "AAL", "American Airlines", "US", "Oneworld"),
    ("DL", "DAL", "Delta Air Lines", "US", "SkyTeam"),
    ("UA", "UAL", "United Airlines", "US", "Star Alliance"),
    ("WN", "SWA", "Southwest Airlines", "US", None),
    ("B6", "JBU", "JetBlue Airways", "US", None),
    ("AS", "ASA", "Alaska Airlines", "US", "Oneworld"),
    ("F9", "FFT", "Frontier Airlines", "US", None),
    ("NK", "NKS", "Spirit Airlines", "US", None),
    ("HA", "HAL", "Hawaiian Airlines", "US", None),
    ("AC", "ACA", "Air Canada", "CA", "Star Alliance"),
    ("WS", "WJA", "WestJet", "CA", None),
    # Europe
    ("BA", "BAW", "British Airways", "GB", "Oneworld"),
    ("LH", "DLH", "Lufthansa", "DE", "Star Alliance"),
    ("AF", "AFR", "Air France", "FR", "SkyTeam"),
    ("KL", "KLM", "KLM Royal Dutch Airlines", "NL", "SkyTeam"),
    ("IB", "IBE", "Iberia", "ES", "Oneworld"),
    ("AZ", "ITY", "ITA Airways", "IT", "SkyTeam"),
    ("VS", "VIR", "Virgin Atlantic", "GB", "SkyTeam"),
    ("U2", "EZY", "easyJet", "GB", None),
    ("FR", "RYR", "Ryanair", "IE", None),
    ("SK", "SAS", "SAS Scandinavian", "SE", "Star Alliance"),
    ("DY", "NAX", "Norwegian Air Shuttle", "NO", None),
    ("TP", "TAP", "TAP Air Portugal", "PT", "Star Alliance"),
    ("AY", "FIN", "Finnair", "FI", "Oneworld"),
    ("EI", "EIN", "Aer Lingus", "IE", "Oneworld"),
    ("LX", "SWR", "SWISS", "CH", "Star Alliance"),
    ("OS", "AUA", "Austrian Airlines", "AT", "Star Alliance"),
    # Asia/Pacific
    ("NH", "ANA", "All Nippon Airways", "JP", "Star Alliance"),
    ("JL", "JAL", "Japan Airlines", "JP", "Oneworld"),
    ("SQ", "SIA", "Singapore Airlines", "SG", "Star Alliance"),
    ("CX", "CPA", "Cathay Pacific", "HK", "Oneworld"),
    ("TG", "THA", "Thai Airways", "TH", "Star Alliance"),
    ("QF", "QFA", "Qantas", "AU", "Oneworld"),
    ("VA", "VOZ", "Virgin Australia", "AU", None),
    ("AI", "AIC", "Air India", "IN", "Star Alliance"),
    ("KE", "KAL", "Korean Air", "KR", "SkyTeam"),
    ("OZ", "AAR", "Asiana Airlines", "KR", "Star Alliance"),
    ("CI", "CAL", "China Airlines", "TW", "SkyTeam"),
    ("BR", "EVA", "EVA Air", "TW", "Star Alliance"),
    ("CA", "CCA", "Air China", "CN", "Star Alliance"),
    ("CZ", "CSN", "China Southern", "CN", "SkyTeam"),
    ("MU", "CES", "China Eastern", "CN", "SkyTeam"),
    # Middle East
    ("EK", "UAE", "Emirates", "AE", None),
    ("QR", "QTR", "Qatar Airways", "QA", "Oneworld"),
    ("EY", "ETD", "Etihad Airways", "AE", None),
    ("SV", "SVA", "Saudia", "SA", "SkyTeam"),
    ("TK", "THY", "Turkish Airlines", "TR", "Star Alliance"),
    # Africa
    ("SA", "SAA", "South African Airways", "ZA", "Star Alliance"),
    ("ET", "ETH", "Ethiopian Airlines", "ET", "Star Alliance"),
    ("KQ", "KQA", "Kenya Airways", "KE", "SkyTeam"),
    ("MS", "MSR", "EgyptAir", "EG", "Star Alliance"),
    # LatAm
    ("LA", "LAN", "LATAM Airlines", "CL", "Oneworld"),
    ("AM", "AMX", "Aeromexico", "MX", "SkyTeam"),
    ("AV", "AVA", "Avianca", "CO", "Star Alliance"),
    ("CM", "CMP", "Copa Airlines", "PA", "Star Alliance"),
    ("G3", "GLO", "Gol Linhas Aereas", "BR", None),
]


def build_airlines() -> pl.DataFrame:
    """Return the silver `airlines` reference table."""
    return pl.DataFrame(
        _AIRLINES,
        schema=["iata", "icao", "name", "country_iso", "alliance"],
        orient="row",
    )
