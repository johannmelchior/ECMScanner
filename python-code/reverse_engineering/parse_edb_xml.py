"""
parse_edb_xml.py
Parses the edb.xml file captured from BUDS2's temp directory (%TEMP%\Temp\EdbDump\edb.xml)
Extracts the complete Engineering Database: vehicles, ECUs, diagnostic items, DTCs, firmware.

HOW TO GET edb.xml:
  1. Run capture_edb_temp.ps1 (in this folder)
  2. Start BUDS2 — wait for it to finish loading
  3. The script copies edb.xml to python-code/output/edb/
  4. Then run this script
"""
import os, json, xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

EDB_PATH = Path(r"C:\Users\johan\Documents\projetoCAN\python-code\output\edb\edb.xml")
OUT_DIR  = Path(r"C:\Users\johan\Documents\projetoCAN\python-code\output")

# Load translation DB for human-readable labels
TRANS_FILE = OUT_DIR / "buds2_translations.json"
translations = {}
if TRANS_FILE.exists():
    with open(TRANS_FILE, encoding="utf-8") as f:
        raw = json.load(f)
        translations = {k: v.get("pt") or v.get("en", k) for k, v in raw.items()}

def t(key):
    """Translate a TI_ key to human-readable."""
    if key and f"TI_{key}" in translations:
        return translations[f"TI_{key}"]
    return translations.get(key, key)

def ns(tag):
    """Strip XML namespace from tag."""
    return tag.split("}")[-1] if "}" in tag else tag

def parse_edb(path):
    print(f"[*] Parsing: {path}")
    tree = ET.parse(path)
    root = tree.getroot()
    print(f"[*] Root tag: {root.tag}")

    # Collect namespace map
    used_ns = set()
    for el in root.iter():
        used_ns.add(el.tag.split("}")[0].lstrip("{") if "}" in el.tag else "")

    print(f"[*] Namespaces used: {used_ns}")

    # ── ECU Variants / Models ────────────────────────────────────────────────
    ecus = []
    for el in root.iter():
        tag = ns(el.tag)
        if tag in ("EcuVariant", "BaseVariant", "VehicleEcm"):
            ecu = {
                "tag": tag,
                "shortName": el.get("shortName", el.get("name", "")),
            }
            # Grab child names
            for child in el:
                ctag = ns(child.tag)
                cval = child.text or child.get("value", "")
                if cval:
                    ecu[ctag] = cval
            ecus.append(ecu)

    print(f"[*] ECU Variants/Base Variants: {len(ecus)}")

    # ── Diagnostic Data Items (PIDs) ─────────────────────────────────────────
    pids = []
    for el in root.iter():
        tag = ns(el.tag)
        if tag in ("DiagnosticDataItem", "DiagnosticDataItemClassA", "DiagnosticDataItemClassB"):
            pid = {
                "tag": tag,
                "shortName": el.get("shortName", ""),
                "label": t(el.get("shortName", "")),
            }
            for child in el:
                ctag = ns(child.tag)
                cval = child.text or ""
                if cval.strip():
                    pid[ctag] = cval.strip()
            pids.append(pid)

    print(f"[*] Diagnostic Data Items: {len(pids)}")

    # ── DTCs ─────────────────────────────────────────────────────────────────
    dtcs = []
    for el in root.iter():
        tag = ns(el.tag)
        if tag in ("Dtc", "BrpDtc", "SaeDtc"):
            dtc = {
                "tag": tag,
                "shortName": el.get("shortName", ""),
                "label": t(el.get("shortName", "")),
                "code": el.get("code", el.get("dtcCode", "")),
            }
            dtcs.append(dtc)

    print(f"[*] DTCs: {len(dtcs)}")

    # ── Firmware Files ────────────────────────────────────────────────────────
    firmwares = []
    for el in root.iter():
        tag = ns(el.tag)
        if tag == "Firmware":
            fw = {
                "name": el.get("fileName", el.get("shortName", "")),
                "type": el.get("fileType", ""),
                "checksum": el.get("checksum", el.get("crc", "")),
            }
            firmwares.append(fw)

    print(f"[*] Firmware entries: {len(firmwares)}")

    # ── Models / Vehicles ─────────────────────────────────────────────────────
    models = []
    for el in root.iter():
        tag = ns(el.tag)
        if tag in ("Model", "Product", "VehicleVersion", "BaseVariant"):
            m = {
                "tag": tag,
                "name": el.get("shortName", el.get("name", "")),
            }
            models.append(m)

    print(f"[*] Models/Products: {len(models)}")

    return {
        "ecus": ecus,
        "pids": pids,
        "dtcs": dtcs,
        "firmwares": firmwares,
        "models": models,
    }

def print_summary(data):
    # Sea-Doo ECUs
    sea_ecus = [e for e in data["ecus"] if "sea" in str(e).lower() or "SEA" in str(e)]
    print(f"\n=== Sea-Doo related ECUs ({len(sea_ecus)}) ===")
    for e in sea_ecus[:20]:
        print(f"  {e.get('shortName', '')} [{e['tag']}]")

    # Sea-Doo PIDs
    sea_pids = [p for p in data["pids"] if "sea" in str(p).lower() or
                "ibr" in str(p).lower() or "vts" in str(p).lower()]
    print(f"\n=== Sea-Doo PIDs ({len(sea_pids)}) ===")
    for p in sea_pids[:30]:
        print(f"  {p.get('shortName', ''):40s} | {p.get('label', '')}")

    # First 20 PIDs
    print(f"\n=== First 20 of {len(data['pids'])} all PIDs ===")
    for p in data["pids"][:20]:
        print(f"  {p.get('shortName', ''):40s} | {p.get('label', '')}")

    # First 20 DTCs
    print(f"\n=== First 20 of {len(data['dtcs'])} DTCs ===")
    for d in data["dtcs"][:20]:
        print(f"  {d.get('code', ''):10s} {d.get('shortName', ''):40s} | {d.get('label', '')}")

if __name__ == "__main__":
    if not EDB_PATH.exists():
        print(f"\n[!] edb.xml not found at: {EDB_PATH}")
        print("[!] Steps to get it:")
        print("    1. Open PowerShell as Admin")
        print(f"    2. Run: powershell -ExecutionPolicy Bypass -File C:\\Users\\johan\\Documents\\projetoCAN\\python-code\\capture_edb_temp.ps1")
        print("    3. Launch BUDS2 in another window and wait for it to fully load")
        print("    4. The script will copy edb.xml automatically")
        print("    5. Then re-run this script\n")
    else:
        data = parse_edb(EDB_PATH)
        print_summary(data)

        # Save structured outputs
        for key, val in data.items():
            if val:
                out_path = OUT_DIR / f"edb_{key}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(val, f, ensure_ascii=False, indent=2)
                print(f"\n[+] Saved {len(val):,} {key} -> {out_path}")

        print("\n[*] Done.")
