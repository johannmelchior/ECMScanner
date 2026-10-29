"""
Extract packet semantics from BRP EDB XML.

This extractor focuses on diagnostic CAN semantics present in EDB:
- Module identity (name/longNameTi/uuid)
- Request/response CAN IDs
- Functional request support
- Extended addressing profile (requestExtendedId/responseExtendedId)

Output:
- python-code/ecm_scanner/brp_packet_semantics_from_edb.json
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

EDB_XML = Path(r"c:/Users/johan/Documents/projetoCAN/temp_7z/keygen2/edb_extracted/edb.xml")
OUT_JSON = Path(r"c:/Users/johan/Documents/projetoCAN/python-code/ecm_scanner/brp_packet_semantics_from_edb.json")


@dataclass
class OdxVariant:
    name: str
    long_name_ti: str
    uuid: str
    start_of_use: str
    requested_can_id: str
    response_can_id: str
    extended_id: bool
    functional_request: bool
    functional_requested_can_id: str
    request_extended_id: str
    response_extended_id: str


def _to_hex(value: str) -> str:
    value = (value or "").strip().upper()
    return f"0x{value}" if value else ""


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def parse_odx_variants(path: Path) -> list[OdxVariant]:
    variants: list[OdxVariant] = []
    for _, el in ET.iterparse(path, events=("end",)):
        tag = el.tag.split("}")[-1]
        if tag != "odxBaseVariants":
            el.clear()
            continue

        variants.append(
            OdxVariant(
                name=(el.get("name") or "").strip(),
                long_name_ti=(el.get("longNameTi") or "").strip(),
                uuid=(el.get("uuid") or "").strip(),
                start_of_use=(el.get("startOfUse") or "").strip(),
                requested_can_id=_to_hex(el.get("requestedCanId") or ""),
                response_can_id=_to_hex(el.get("responseCanId") or ""),
                extended_id=_to_bool(el.get("extendedId") or "false"),
                functional_request=_to_bool(el.get("functionalRequest") or "false"),
                functional_requested_can_id=_to_hex(el.get("functionalRequestedCanId") or ""),
                request_extended_id=_to_hex(el.get("requestExtendedId") or ""),
                response_extended_id=_to_hex(el.get("responseExtendedId") or ""),
            )
        )
        el.clear()
    return variants


def build_semantics(variants: list[OdxVariant]) -> dict:
    by_response = defaultdict(lambda: {
        "request_ids": set(),
        "module_short_names": set(),
        "module_names": set(),
        "functional_request_ids": set(),
        "extended_modes": set(),
        "request_extended_ids": set(),
        "response_extended_ids": set(),
        "uuids": set(),
        "start_of_use": set(),
        "entries": 0,
    })

    by_request = defaultdict(lambda: {
        "response_ids": set(),
        "module_short_names": set(),
        "module_names": set(),
        "functional_request_ids": set(),
        "extended_modes": set(),
        "request_extended_ids": set(),
        "response_extended_ids": set(),
        "uuids": set(),
        "entries": 0,
    })

    pairs = defaultdict(lambda: {
        "module_short_names": set(),
        "module_names": set(),
        "functional_request_ids": set(),
        "extended_modes": set(),
        "request_extended_ids": set(),
        "response_extended_ids": set(),
        "uuids": set(),
        "start_of_use": set(),
        "entries": 0,
    })

    modules = {}

    for v in variants:
        if not v.requested_can_id or not v.response_can_id:
            continue

        mod_key = f"{v.long_name_ti}|{v.name}|{v.requested_can_id}|{v.response_can_id}|{v.request_extended_id}|{v.response_extended_id}"
        modules[mod_key] = {
            "short_name": v.long_name_ti,
            "name": v.name,
            "uuid": v.uuid,
            "start_of_use": v.start_of_use,
            "request_id": v.requested_can_id,
            "response_id": v.response_can_id,
            "functional_request": v.functional_request,
            "functional_request_id": v.functional_requested_can_id,
            "extended_id": v.extended_id,
            "request_extended_id": v.request_extended_id,
            "response_extended_id": v.response_extended_id,
        }

        info_resp = by_response[v.response_can_id]
        info_resp["request_ids"].add(v.requested_can_id)
        info_resp["module_short_names"].add(v.long_name_ti)
        info_resp["module_names"].add(v.name)
        if v.functional_requested_can_id:
            info_resp["functional_request_ids"].add(v.functional_requested_can_id)
        info_resp["extended_modes"].add("extended" if v.extended_id else "standard")
        if v.request_extended_id:
            info_resp["request_extended_ids"].add(v.request_extended_id)
        if v.response_extended_id:
            info_resp["response_extended_ids"].add(v.response_extended_id)
        if v.uuid:
            info_resp["uuids"].add(v.uuid)
        if v.start_of_use:
            info_resp["start_of_use"].add(v.start_of_use)
        info_resp["entries"] += 1

        info_req = by_request[v.requested_can_id]
        info_req["response_ids"].add(v.response_can_id)
        info_req["module_short_names"].add(v.long_name_ti)
        info_req["module_names"].add(v.name)
        if v.functional_requested_can_id:
            info_req["functional_request_ids"].add(v.functional_requested_can_id)
        info_req["extended_modes"].add("extended" if v.extended_id else "standard")
        if v.request_extended_id:
            info_req["request_extended_ids"].add(v.request_extended_id)
        if v.response_extended_id:
            info_req["response_extended_ids"].add(v.response_extended_id)
        if v.uuid:
            info_req["uuids"].add(v.uuid)
        info_req["entries"] += 1

        pair_key = f"{v.requested_can_id}->{v.response_can_id}"
        pair = pairs[pair_key]
        pair["module_short_names"].add(v.long_name_ti)
        pair["module_names"].add(v.name)
        if v.functional_requested_can_id:
            pair["functional_request_ids"].add(v.functional_requested_can_id)
        pair["extended_modes"].add("extended" if v.extended_id else "standard")
        if v.request_extended_id:
            pair["request_extended_ids"].add(v.request_extended_id)
        if v.response_extended_id:
            pair["response_extended_ids"].add(v.response_extended_id)
        if v.uuid:
            pair["uuids"].add(v.uuid)
        if v.start_of_use:
            pair["start_of_use"].add(v.start_of_use)
        pair["entries"] += 1

    def finalize(d: dict) -> dict:
        out = {}
        for k, v in sorted(d.items()):
            out[k] = {
                kk: sorted(list(vv)) if isinstance(vv, set) else vv
                for kk, vv in v.items()
            }
        return out

    semantics = {
        "source": str(EDB_XML).replace("\\", "/"),
        "schema_note": "Diagnostic semantics from odxBaseVariants. This maps diagnostic packet addressing, not runtime broadcast signal decoding.",
        "counts": {
            "odx_variants": len(variants),
            "module_entries": len(modules),
            "unique_request_ids": len(by_request),
            "unique_response_ids": len(by_response),
            "unique_request_response_pairs": len(pairs),
        },
        "modules": sorted(modules.values(), key=lambda x: (x["response_id"], x["request_id"], x["short_name"], x["name"])),
        "by_response_id": finalize(by_response),
        "by_request_id": finalize(by_request),
        "by_request_response_pair": finalize(pairs),
    }
    return semantics


def main() -> None:
    if not EDB_XML.exists():
        raise SystemExit(f"EDB XML not found: {EDB_XML}")

    variants = parse_odx_variants(EDB_XML)
    semantics = build_semantics(variants)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(semantics, f, ensure_ascii=False, indent=2)

    print(f"Generated: {OUT_JSON}")
    print(f"ODX variants: {semantics['counts']['odx_variants']}")
    print(f"Request IDs: {semantics['counts']['unique_request_ids']}")
    print(f"Response IDs: {semantics['counts']['unique_response_ids']}")
    print(f"Pairs: {semantics['counts']['unique_request_response_pairs']}")


if __name__ == "__main__":
    main()
