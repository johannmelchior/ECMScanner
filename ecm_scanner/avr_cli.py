from __future__ import annotations

import argparse
from typing import Sequence

from avr_interface import AvrTransport, DEFAULT_BAUDRATE, InterfaceMode


def parse_hex_bytes(values: Sequence[str]) -> bytes:
    return bytes(int(value, 16) for value in values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PC tool for the ATmega162 FT245RL diagnostic bridge")
    parser.add_argument("--port", required=True, help="Serial port, ex.: COM5")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE,
                        help=f"FT245 serial bridge speed on PC side (default: {DEFAULT_BAUDRATE})")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("info")
    subparsers.add_parser("mode")

    mode_parser = subparsers.add_parser("set-mode")
    mode_parser.add_argument("mode", choices=["idle", "kline", "can"])

    kbaud_parser = subparsers.add_parser("kline-set-baud")
    kbaud_parser.add_argument("baud", type=int)
    subparsers.add_parser("kline-wakeup")

    ktx_parser = subparsers.add_parser("kline-tx")
    ktx_parser.add_argument("value", type=lambda text: int(text, 0))

    krx_parser = subparsers.add_parser("kline-rx")
    krx_parser.add_argument("timeout", type=int, nargs="?", default=100)

    khigh_parser = subparsers.add_parser("kline-wait-high", help="wait for a low->high K-Line transition")
    khigh_parser.add_argument("timeout", type=int, nargs="?", default=30000)
    khigh_parser.add_argument("stable", type=int, nargs="?", default=20)

    kdebug_parser = subparsers.add_parser("kline-debug")
    kdebug_parser.add_argument("observe", type=int, nargs="?", default=120)

    canb_parser = subparsers.add_parser("can-set-bitrate")
    canb_parser.add_argument("kbps", type=int)

    cantx_parser = subparsers.add_parser("can-tx")
    cantx_parser.add_argument("can_id", type=lambda text: int(text, 0))
    cantx_parser.add_argument("data", nargs="*", default=[])

    subparsers.add_parser("can-rx")
    subparsers.add_parser("can-status")
    return parser


def mode_from_string(value: str) -> InterfaceMode:
    return {
        "idle": InterfaceMode.IDLE,
        "kline": InterfaceMode.KLINE,
        "can": InterfaceMode.CAN,
    }[value]


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    with AvrTransport(args.port, baudrate=args.baudrate) as transport:
        if args.command == "info":
            info = transport.get_info()
            print(f"proto=0x{info['proto_version']:02X} mode=0x{info['mode']:02X}")
            return

        if args.command == "mode":
            mode = transport.get_mode()
            print(mode.name.lower())
            return

        if args.command == "set-mode":
            transport.set_mode(mode_from_string(args.mode))
            print("ok")
            return

        if args.command == "kline-set-baud":
            transport.set_mode(InterfaceMode.KLINE)
            transport.kline_set_baud(args.baud)
            print("ok")
            return

        if args.command == "kline-wakeup":
            transport.set_mode(InterfaceMode.KLINE)
            transport.kline_wakeup()
            print("ok")
            return

        if args.command == "kline-tx":
            transport.set_mode(InterfaceMode.KLINE)
            transport.kline_tx_byte(args.value)
            print("ok")
            return

        if args.command == "kline-rx":
            transport.set_mode(InterfaceMode.KLINE)
            value = transport.kline_rx_byte(args.timeout)
            print("timeout" if value is None else f"0x{value:02X}")
            return

        if args.command == "kline-wait-high":
            transport.set_mode(InterfaceMode.KLINE)
            ok = transport.kline_wait_high(args.timeout, args.stable)
            print("rise-detected" if ok else "timeout")
            return

        if args.command == "kline-debug":
            transport.set_mode(InterfaceMode.KLINE)
            status = transport.kline_get_status(args.observe)
            print(
                f"state={status.state_name} high_ms={status.high_ms} low_ms={status.low_ms} "
                f"edges={status.edge_count} rx_bytes={status.rx_byte_count}"
            )
            return

        if args.command == "can-set-bitrate":
            transport.set_mode(InterfaceMode.CAN)
            transport.can_set_bitrate(args.kbps)
            print("ok")
            return

        if args.command == "can-tx":
            transport.set_mode(InterfaceMode.CAN)
            payload = parse_hex_bytes(args.data)
            transport.can_tx_std(args.can_id, payload)
            print("ok")
            return

        if args.command == "can-rx":
            transport.set_mode(InterfaceMode.CAN)
            frame = transport.can_rx_poll()
            if frame is None:
                print("no-data")
            else:
                hex_data = " ".join(f"{value:02X}" for value in frame.data)
                print(f"id=0x{frame.can_id:03X} data={hex_data}")
            return

        if args.command == "can-status":
            transport.set_mode(InterfaceMode.CAN)
            status = transport.can_get_status()
            flags = []
            if status.bus_off:
                flags.append("BUS_OFF")
            if status.error_warning:
                flags.append("ERROR_WARNING")
            if status.data_overrun:
                flags.append("DATA_OVERRUN")
            if status.rx_buffer_has_data:
                flags.append("RX_PENDING")
            if status.tx_buffer_free:
                flags.append("TX_READY")
            if status.tx_complete:
                flags.append("TX_COMPLETE")
            print(
                f"bitrate={status.bitrate_kbps}kbps sr=0x{status.status:02X} "
                f"rxerr={status.rx_error_counter} txerr={status.tx_error_counter} "
                f"rmc={status.rx_message_count} ecc=0x{status.error_code_capture:02X} "
                f"alc=0x{status.arbitration_lost_capture:02X} ewl={status.error_warning_limit} "
                f"flags={','.join(flags) if flags else 'none'}"
            )
            return

        parser.error(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()