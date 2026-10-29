import argparse
import collections
import importlib.util
import json
import serial
import struct
import time
from pathlib import Path


def load_kline_module():
    spec = importlib.util.spec_from_file_location(
        "_kline_read", r"z:\projetoCAN\python-code\_kline_read.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def capture_stage(label: str, seconds: float, wake: bool) -> tuple[dict, list[dict]]:
    mod = load_kline_module()
    ser = serial.Serial(mod.PORT, mod.BAUD, timeout=0.04)
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    version, mode = mod.get_info(ser)
    if version is None:
        ser.close()
        raise RuntimeError("AVR nao respondeu GET_INFO")
    if mode != 1:
        ser.close()
        raise RuntimeError(f"AVR nao esta em KLINE (mode={mode})")

    if wake:
        mod.do_wakeup(ser)
        time.sleep(0.1)

    ser.reset_input_buffer()

    bulk_payload = struct.pack(
        "<HHB",
        mod.BULK_FIRST_TIMEOUT_MS,
        mod.BULK_INTER_TIMEOUT_MS,
        mod.BULK_MAX_BYTES,
    )

    frames = []
    frame_buf = bytearray()
    byte_hist = collections.Counter()
    frame_hist = collections.Counter()
    last_bulk_t = time.monotonic()
    t_start = time.monotonic()
    deadline = t_start + seconds

    def flush_frame(now: float) -> None:
        if not frame_buf:
            return
        fr = bytes(frame_buf)
        frame_hex = fr.hex(" ").upper()
        frames.append(
            {
                "t": round(now - t_start, 3),
                "len": len(fr),
                "hex": frame_hex,
                "sync": mod._detect_sync(fr),
                "checksum": mod._checksum_ok(fr),
                "inv_hex": bytes(b ^ 0xFF for b in fr).hex(" ").upper(),
            }
        )
        frame_hist[frame_hex] += 1
        frame_buf.clear()

    try:
        while time.monotonic() < deadline:
            mod.send_pkt(ser, mod.CMD_KLINE_BULK, bulk_payload)
            resp = mod.recv_pkt(
                ser,
                mod.CMD_KLINE_BULK,
                timeout=(mod.BULK_FIRST_TIMEOUT_MS + mod.BULK_MAX_BYTES * 2) / 1000 + 0.5,
            )
            now = time.monotonic()

            if resp and len(resp) >= 2 and resp[0] == mod.RSP_OK:
                count = resp[1]
                chunk = resp[2 : 2 + count]
                gap_ms = (now - last_bulk_t) * 1000.0
                if count > 0:
                    if frame_buf and gap_ms > mod.FRAME_GAP_MS:
                        flush_frame(now)
                    frame_buf.extend(chunk)
                    for b in chunk:
                        byte_hist[b] += 1
                    last_bulk_t = now
                elif frame_buf and (now - last_bulk_t) * 1000.0 > mod.FRAME_GAP_MS * 3:
                    flush_frame(now)
            elif frame_buf:
                flush_frame(now)
    finally:
        flush_frame(time.monotonic())
        ser.close()

    elapsed = max(time.monotonic() - t_start, 0.001)
    top_frames = [
        {"count": count, "len": len(bytes.fromhex(frame_hex)), "hex": frame_hex}
        for frame_hex, count in frame_hist.most_common(10)
    ]
    top_bytes = [
        {"byte": f"0x{value:02X}", "count": count, "pct": round(count * 100.0 / sum(byte_hist.values()), 2)}
        for value, count in byte_hist.most_common(12)
    ] if byte_hist else []

    summary = {
        "label": label,
        "seconds": round(elapsed, 3),
        "wake": wake,
        "port": mod.PORT,
        "baud": mod.BAUD,
        "firmware_version": version,
        "mode": mode,
        "frames": len(frames),
        "bytes": sum(byte_hist.values()),
        "bytes_per_second": round(sum(byte_hist.values()) / elapsed, 2),
        "unique_frame_shapes": len(frame_hist),
        "length_histogram": dict(sorted(collections.Counter(f["len"] for f in frames).items())),
        "top_bytes": top_bytes,
        "top_frames": top_frames,
    }
    return summary, frames


def main() -> int:
    parser = argparse.ArgumentParser(description="Captura K-Line por etapa")
    parser.add_argument("--label", required=True, help="Nome da etapa")
    parser.add_argument("--seconds", type=float, default=20.0, help="Duracao da captura em segundos")
    parser.add_argument("--wake", action="store_true", help="Executa wakeup Yamaha antes da captura")
    args = parser.parse_args()

    out_dir = Path(r"z:\projetoCAN\python-code\captures\kline")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in args.label.lower())

    summary, frames = capture_stage(args.label, args.seconds, args.wake)

    summary_path = out_dir / f"{stamp}_{safe_label}_summary.json"
    frames_path = out_dir / f"{stamp}_{safe_label}_frames.jsonl"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with frames_path.open("w", encoding="utf-8") as handle:
        for frame in frames:
            handle.write(json.dumps(frame, ensure_ascii=True) + "\n")

    print(json.dumps(summary, indent=2))
    print(f"summary_file={summary_path}")
    print(f"frames_file={frames_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())