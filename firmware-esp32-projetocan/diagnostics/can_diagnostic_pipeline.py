import csv
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime


def _parse_ts(ts: str):
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def analyze_folder(log_dir: Path, odx_csv: Path, out_dir: Path, profile_name: str):
    files = sorted(log_dir.glob("can_log_*.csv"))
    if not files:
        raise FileNotFoundError(f"Nenhum can_log_*.csv em {log_dir}")

    req_lookup = defaultdict(list)
    resp_lookup = defaultdict(list)
    if odx_csv.exists():
        with odx_csv.open("r", encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            for r in rd:
                req = (r.get("RequestedCanId") or "").strip().upper()
                rsp = (r.get("ResponseCanId") or "").strip().upper()
                mod = f"{(r.get('Name') or '').strip()} [{(r.get('LongName') or '').strip()}]"
                if req:
                    req_lookup[req].append(mod)
                if rsp:
                    resp_lookup[rsp].append(mod)

    frames = []
    id_counter = Counter()
    uds_counter = Counter()
    active_files = set()
    timing_deltas = defaultdict(list)

    for fp in files:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            rows = list(rd)

        valid = [r for r in rows if (r.get("ID") or "").strip()]
        if not valid:
            continue

        active_files.add(fp.name)
        by_id_ts = defaultdict(list)

        for r in valid:
            can_id = (r.get("ID") or "").strip().upper()
            dlc = (r.get("DLC") or "").strip()
            data = (r.get("Data") or "").strip().upper()
            ts = (r.get("Timestamp") or "").strip()

            b = [x for x in data.split(" ") if x]
            sid = ""
            if len(b) >= 2 and len(b[1]) == 2:
                sid = b[1]
                uds_counter[sid] += 1

            frames.append((fp.name, ts, can_id, dlc, data, sid))
            id_counter[can_id] += 1

            dtt = _parse_ts(ts)
            if dtt is not None:
                by_id_ts[can_id].append(dtt)

        for cid, tlist in by_id_ts.items():
            tlist.sort()
            for i in range(1, len(tlist)):
                dt_ms = (tlist[i] - tlist[i - 1]).total_seconds() * 1000.0
                if 0 < dt_ms < 60000:
                    timing_deltas[cid].append(dt_ms)

    if not frames:
        raise RuntimeError("Sem frames validos para analise")

    total = len(frames)
    unique_ids = len(id_counter)

    id_rows = []
    for cid, cnt in id_counter.most_common():
        req = sorted(set(req_lookup.get(cid, [])))
        rsp = sorted(set(resp_lookup.get(cid, [])))
        file_count = len({fn for fn, _, idv, *_ in frames if idv == cid})
        id_rows.append(
            {
                "ID": cid,
                "Frames": cnt,
                "PctOfTotal": round(cnt * 100.0 / total, 3),
                "FilesPresent": file_count,
                "OdxAsRequest": " | ".join(req),
                "OdxAsResponse": " | ".join(rsp),
            }
        )

    uds_rows = []
    for sid, cnt in uds_counter.most_common():
        uds_rows.append(
            {
                "SID": sid,
                "Frames": cnt,
                "PctOfTotal": round(cnt * 100.0 / total, 3),
            }
        )

    timing_rows = []
    for cid, deltas in sorted(
        timing_deltas.items(),
        key=lambda x: (sum(x[1]) / len(x[1])) if x[1] else 1e12,
    ):
        if not deltas:
            continue
        avg = sum(deltas) / len(deltas)
        timing_rows.append(
            {
                "ID": cid,
                "Samples": len(deltas),
                "AvgPeriodMs": round(avg, 3),
                "MinPeriodMs": round(min(deltas), 3),
                "MaxPeriodMs": round(max(deltas), 3),
                "EstHz": round(1000.0 / avg, 3) if avg > 0 else 0.0,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    id_csv = out_dir / f"{profile_name}_CAN_ID_Summary.csv"
    uds_csv = out_dir / f"{profile_name}_UDS_Summary.csv"
    timing_csv = out_dir / f"{profile_name}_CAN_ID_Timing.csv"
    md = out_dir / f"{profile_name}_CAN_Analysis.md"

    with id_csv.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(id_rows[0].keys()))
        wr.writeheader()
        wr.writerows(id_rows)

    with uds_csv.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["SID", "Frames", "PctOfTotal"])
        wr.writeheader()
        wr.writerows(uds_rows)

    if timing_rows:
        with timing_csv.open("w", encoding="utf-8", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(timing_rows[0].keys()))
            wr.writeheader()
            wr.writerows(timing_rows)

    lines = []
    lines.append(f"# Analise Completa - {profile_name}")
    lines.append("")
    lines.append(f"- Arquivos encontrados: {len(files)}")
    lines.append(f"- Arquivos com frames validos: {len(active_files)}")
    lines.append(f"- Frames totais: {total}")
    lines.append(f"- IDs unicos: {unique_ids}")
    lines.append("")
    lines.append("## Top IDs")
    for r in id_rows[:20]:
        lines.append(f"- ID {r['ID']}: {r['Frames']} frames ({r['PctOfTotal']}%)")
    lines.append("")
    lines.append("## Top SID (byte 2)")
    for r in uds_rows[:15]:
        lines.append(f"- SID 0x{r['SID']}: {r['Frames']} frames ({r['PctOfTotal']}%)")

    md.write_text("\n".join(lines), encoding="utf-8")

    return {
        "files": len(files),
        "active_files": len(active_files),
        "total_frames": total,
        "unique_ids": unique_ids,
        "id_csv": str(id_csv),
        "uds_csv": str(uds_csv),
        "timing_csv": str(timing_csv),
        "report_md": str(md),
    }


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    result = analyze_folder(
        log_dir=base / "logs" / "BRP-SEADOO-GTX-2022-300hp",
        odx_csv=base.parent / "docs" / "seadoo_odx_can_map.csv",
        out_dir=base.parent / "docs",
        profile_name="BRP_SEADOO_GTX_2022_300hp",
    )
    print(result)
