"""
parse_odx_properties.py
Parses the accessible BUDS2 ODX and BRP properties files into a structured
searchable JSON database for Sea-Doo CAN signal analysis.
"""
import os, json, re
from pathlib import Path

BUDS2 = Path(r"C:\Program Files (x86)\BRP\BUDS2")
OUT   = Path(r"C:\Users\johan\Documents\projetoCAN\python-code\output")
OUT.mkdir(parents=True, exist_ok=True)

def read_props(path):
    """Read a Java .properties file into a dict (handles unicode escapes)."""
    props = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            # decode Java \uXXXX escapes
            try:
                v = v.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
            except Exception:
                pass
            props[k] = v
    return props

# ── 1. Load all language variants of ODX.properties ─────────────────────────
odx_files = sorted(BUDS2.glob("ODXDataBin/ODX*.properties"))
print(f"[*] Found {len(odx_files)} ODX property files:")
for f in odx_files:
    print(f"    {f.name}  ({f.stat().st_size:,} bytes)")

# Primary: English (no suffix)
odx_en_path = BUDS2 / "ODXDataBin" / "ODX.properties"
odx_pt_path = BUDS2 / "ODXDataBin" / "ODX_pt.properties"

odx_en = read_props(odx_en_path)
odx_pt = read_props(odx_pt_path)
print(f"\n[*] ODX English entries: {len(odx_en):,}")
print(f"[*] ODX Portuguese entries: {len(odx_pt):,}")

# ── 2. Load BRP.properties and BRP_pt.properties ─────────────────────────────
brp_en = read_props(BUDS2 / "workspace" / "BRP.properties")
brp_pt = read_props(BUDS2 / "workspace" / "BRP_pt.properties")
print(f"[*] BRP English entries: {len(brp_en):,}")
print(f"[*] BRP Portuguese entries: {len(brp_pt):,}")

# ── 3. Build merged translation database ─────────────────────────────────────
all_keys = sorted(set(odx_en) | set(odx_pt) | set(brp_en) | set(brp_pt))
db = {}
for k in all_keys:
    db[k] = {
        "en": odx_en.get(k) or brp_en.get(k, ""),
        "pt": odx_pt.get(k) or brp_pt.get(k, ""),
    }

out_all = OUT / "buds2_translations.json"
with open(out_all, "w", encoding="utf-8") as f:
    json.dump(db, f, ensure_ascii=False, indent=2)
print(f"\n[+] Wrote {len(db):,} entries -> {out_all}")

# ── 4. Sea-Doo / IBR / VTS / engine relevant filter ─────────────────────────
SEA_PATTERNS = re.compile(
    r"(sea|seadoo|ibr|vts|iBR|spark|wake|jet|rxt|rxp|gtx|gti|"
    r"engine|rpm|rpm|speed|throttle|fuel|temp|coolant|boost|"
    r"exhaust|clutch|gear|brake|tps|map|baro|iat|clt|ect|"
    r"egt|lambda|knock|injection|ignit|timing|battery|volt|"
    r"current|sensor|ecu|ecm|can|diag|fault|dtc|error|"
    r"actuator|relay|pump|valve|fan|pressure|oil|water|"
    r"accel|gyro|lean|tilt|steer|reverse|trim|vss|abs|"
    r"mode|limit|calibr)",
    re.IGNORECASE,
)

sea_db = {k: v for k, v in db.items() if SEA_PATTERNS.search(k) or
          SEA_PATTERNS.search(v["en"]) or SEA_PATTERNS.search(v["pt"])}

out_sea = OUT / "seadoo_signals.json"
with open(out_sea, "w", encoding="utf-8") as f:
    json.dump(sea_db, f, ensure_ascii=False, indent=2)
print(f"[+] Wrote {len(sea_db):,} Sea-Doo/engine relevant entries -> {out_sea}")

# ── 5. Print a nice Sea-Doo summary ──────────────────────────────────────────
print("\n=== Sea-Doo / IBR / Engine signals (sample) ===")
sample = {k: v for k, v in sea_db.items() if re.search(r"(Sea|IBR|VTS|iBR|Spark|Wake)", k)}
for k, v in sorted(sample.items())[:60]:
    label = v["en"] or v["pt"]
    if label:
        print(f"  {k:55s} = {label}")

# ── 6. Category counts ────────────────────────────────────────────────────────
def count_pattern(pattern, data):
    p = re.compile(pattern, re.IGNORECASE)
    return sum(1 for k, v in data.items() if p.search(k) or p.search(v["en"]))

print("\n=== Category counts in merged DB ===")
cats = {
    "Sea-Doo specific": r"sea|seadoo",
    "IBR": r"\bIBR\b|iBR",
    "Engine": r"engine|rpm|ignit|inject|timing",
    "DTC/Fault": r"dtc|fault|error|diag",
    "Sensors": r"sensor|temp|pressure|voltage|current",
    "Actuators": r"actuator|relay|pump|valve|fan",
    "Speed/Throttle": r"speed|throttle|tps|vss",
    "Calibration": r"calibr|learn|align",
}
for name, pat in cats.items():
    print(f"  {name:25s}: {count_pattern(pat, db):4d}")

print("\n[*] Done.")
