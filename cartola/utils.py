from __future__ import annotations

def coalesce(*vals):
    for v in vals:
        if v is not None:
            return v
    return None

POS_MAP = {
    1: "GOL",
    2: "LAT",
    3: "ZAG",
    4: "MEI",
    5: "ATA",
    6: "TEC",
}
