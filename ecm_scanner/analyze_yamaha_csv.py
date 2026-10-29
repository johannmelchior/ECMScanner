import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


PHASES = {
    "idle_before": (1, 79),
    "engine_on": (80, 164),
    "shutdown": (165, 166),
}


def row_tokens(row):
    return [token.upper() for token in row["Data"].split() if token.strip()]


def extract_pairs(tokens):
    pairs = []
    index = 0
    while index < len(tokens) - 1:
        if tokens[index] != "FC":
            index += 1
            continue

        if index + 3 < len(tokens) and tokens[index + 1] != "FC" and tokens[index + 2] == "FC" and tokens[index + 3] != "FC":
            pairs.append((tokens[index + 1], tokens[index + 3]))
            index += 4
            continue

        if index + 2 < len(tokens) and tokens[index + 1] != "FC" and tokens[index + 2] != "FC":
            pairs.append((tokens[index + 1], tokens[index + 2]))
            index += 3
            continue

        index += 1
    return pairs


def parse_windows(rows_count, windows_arg):
    if not windows_arg:
        phases = dict(PHASES)
        phases["idle_after"] = (167, rows_count)
        return phases

    windows = {}
    for item in windows_arg:
        try:
            name, span = item.split(":", 1)
            start_text, end_text = span.split("-", 1)
            start = int(start_text)
            end = int(end_text)
        except ValueError as exc:
            raise SystemExit(f"invalid window '{item}': use name:start-end") from exc
        windows[name] = (start, end)
    return windows


def collect(rows, start, end):
    ids = Counter()
    values = defaultdict(Counter)
    sequences = defaultdict(list)
    sample_rows = defaultdict(list)

    for row_index in range(start - 1, end):
        tokens = row_tokens(rows[row_index])
        for ident, value in extract_pairs(tokens):
            ids[ident] += 1
            values[ident][value] += 1
            sequences[ident].append((row_index + 1, int(value, 16), value))
            if len(sample_rows[ident]) < 4:
                sample_rows[ident].append((row_index + 1, rows[row_index]["Timestamp"], rows[row_index]["Data"]))

    return ids, values, sequences, sample_rows


def summarize_value_behavior(sequence):
    if not sequence:
        return {"unique": 0, "span": 0, "avg_step": 0.0, "trend_score": 0.0}

    numeric_values = [item[1] for item in sequence]
    if len(numeric_values) == 1:
        return {"unique": 1, "span": 0, "avg_step": 0.0, "trend_score": 0.0}

    steps = [abs(right - left) for left, right in zip(numeric_values, numeric_values[1:])]
    signed_steps = [right - left for left, right in zip(numeric_values, numeric_values[1:])]
    positive = sum(1 for step in signed_steps if step > 0)
    negative = sum(1 for step in signed_steps if step < 0)
    trend_score = abs(positive - negative) / max(len(signed_steps), 1)
    return {
        "unique": len(set(numeric_values)),
        "span": max(numeric_values) - min(numeric_values),
        "avg_step": sum(steps) / max(len(steps), 1),
        "trend_score": trend_score,
    }


def print_candidate_classes(name, ids, values, sequences):
    dynamic = []
    slow = []
    for ident, count in ids.items():
        behavior = summarize_value_behavior(sequences[ident])
        unique = behavior["unique"]
        span = behavior["span"]
        avg_step = behavior["avg_step"]
        trend = behavior["trend_score"]
        score = (count * unique) + span
        if count >= 8 and unique >= 4 and avg_step >= 3.0:
            dynamic.append((score, ident, count, unique, span, avg_step))
        elif count >= 6 and unique >= 2 and trend >= 0.45:
            slow.append((trend, ident, count, unique, span, avg_step))

    print(f"\n=== CANDIDATE CLASSES ({name}) ===")
    print("dynamic candidates (RPM/TPS-like):")
    for _, ident, count, unique, span, avg_step in sorted(dynamic, reverse=True)[:10]:
        tops = ", ".join(value for value, _ in values[ident].most_common(6))
        print(f"  ID {ident}: count={count} unique={unique} span=0x{span:02X} avg_step={avg_step:.1f} values={tops}")
    print("slow-changing candidates (temp/status-like):")
    for _, ident, count, unique, span, avg_step in sorted(slow, reverse=True)[:10]:
        tops = ", ".join(value for value, _ in values[ident].most_common(6))
        print(f"  ID {ident}: count={count} unique={unique} span=0x{span:02X} avg_step={avg_step:.1f} values={tops}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Yamaha FC-id-value patterns by window")
    parser.add_argument("csv_path", help="Path to Yamaha CSV log")
    parser.add_argument(
        "--window",
        action="append",
        help="Named analysis window in the form name:start-end. Can be repeated.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    phases = parse_windows(len(rows), args.window)

    phase_data = {
        name: collect(rows, start, end)
        for name, (start, end) in phases.items()
    }

    active_only = []
    if {"idle_before", "engine_on", "idle_after"}.issubset(phase_data):
        idle_ids = set(phase_data["idle_before"][0]) | set(phase_data["idle_after"][0])
        engine_ids = set(phase_data["engine_on"][0])
        active_only = sorted(engine_ids - idle_ids)

    print("=== PHASE RANGES ===")
    for name, (start, end) in phases.items():
        print(f"{name}: rows {start}-{end}")

    if active_only:
        print("\n=== IDS ONLY WITH ENGINE ON ===")
        print(", ".join(active_only))

    if "engine_on" in phase_data:
        print("\n=== TOP IDS IN ENGINE_ON ===")
        for ident, count in phase_data["engine_on"][0].most_common(16):
            print(f"{ident}: {count}")

    if "engine_on" in phase_data:
        print("\n=== POSSIBLE VALUES BY ID (ENGINE_ON) ===")
        interesting = active_only + [
            ident for ident, _ in phase_data["engine_on"][0].most_common(12)
            if ident not in active_only
        ]
        seen = set()
        for ident in interesting:
            if ident in seen:
                continue
            seen.add(ident)
            counts = phase_data["engine_on"][1].get(ident)
            if not counts:
                continue
            total = sum(counts.values())
            unique = len(counts)
            top_values = ", ".join(f"{value}:{count}" for value, count in counts.most_common(12))
            print(f"ID {ident}: total={total} unique_values={unique} top_values={top_values}")

    if {"idle_before", "engine_on", "idle_after"}.issubset(phase_data):
        engine_ids = set(phase_data["engine_on"][0])
        print("\n=== IDS THAT CHANGE REGIME ===")
        for ident in sorted(engine_ids):
            before = phase_data["idle_before"][0].get(ident, 0)
            on = phase_data["engine_on"][0].get(ident, 0)
            after = phase_data["idle_after"][0].get(ident, 0)
            if on and (before != on or after != on):
                print(f"ID {ident}: before={before} on={on} after={after}")

    if active_only:
        print("\n=== SAMPLE ROWS FOR ACTIVE-ONLY IDS ===")
        for ident in active_only:
            print(f"-- ID {ident} --")
            for row_number, timestamp, data in phase_data["engine_on"][3][ident]:
                print(f"  row {row_number} {timestamp} :: {data}")

    if active_only:
        print("\n=== STRONG CANDIDATES FOR LIVE TELEMETRY ===")
        for ident in active_only:
            total = phase_data["engine_on"][0][ident]
            if total < 8:
                continue
            unique = len(phase_data["engine_on"][1][ident])
            values = ", ".join(value for value, _ in phase_data["engine_on"][1][ident].most_common(8))
            print(f"ID {ident}: count={total} unique_values={unique} values={values}")

    for name, (ids, values, sequences, _) in phase_data.items():
        print_candidate_classes(name, ids, values, sequences)


if __name__ == "__main__":
    main()