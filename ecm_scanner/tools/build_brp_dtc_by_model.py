#!/usr/bin/env python3
"""Gera brp_dtc_by_model.json a partir de sessoes BUDS2 decifradas.

Cada ficheiro .buds2/.buds3 pertence a UM modelo de veiculo e contem, por ECU
(``<devices ... deviceName="ECM" ecuVariantName="EV_...">``), os DTCs que estavam
presentes nessa sessao (``<errors xsi:type="dtc:DTC" name="P0112" status="2">``).

O resultado e uma base com dimensao de modelo, que o main.py usa para escolher a
descricao correta em vez da tabela generica brp_dtc_codes.json.

Uso:
    python tools/build_brp_dtc_by_model.py --xml-dir ../sessions_decrypted
    python tools/build_brp_dtc_by_model.py --buds2-dir "C:/Program Files (x86)/BRP/BUDS2/Files" \
        --keys-file buds2_keys.json

O modo --buds2-dir precisa de pycryptodome (ver requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "brp_dtc_by_model.json")

# deviceName ausente/desconhecido -> nao entra na assinatura de ECUs
SKIP_MODULES = {"", "?", "GPS", "GPScan", "GPSCAN", "CCK", "RFComm"}

RE_CREATED = re.compile(r'createdOn="([^"]*)"')
RE_DEVICE = re.compile(r"<devices\s([^>]*)>")
RE_DEV_ATTR = re.compile(r'(\w+)="([^"]*)"')
RE_ERROR = re.compile(r'<errors\s+xsi:type="dtc:DTC"([^>]*)>')
RE_ERR_ATTR = re.compile(r'(\w+)="([^"]*)"')
RE_MY = re.compile(r"MY(\d{2})(?![0-9])", re.IGNORECASE)
RE_VIN_STEM = re.compile(r"^YDV[0-9A-Z]+", re.IGNORECASE)
RE_TIMESTAMP_STEM = re.compile(r"^\d{14}$")
# os ficheiros demo trazem lixo de indice interno colado a descricao
RE_DESC_NOISE = re.compile(r"#+DIAGNOSTICDATAITEMCLASS\w*", re.IGNORECASE)


RE_VIN = re.compile(r'name="PA_VehicleIdentificationNumber" value="([^"]+)"')
# VINs de preenchimento usados nos ficheiros demo
DUMMY_VINS = {"ABCDEFG1234567890"}


def clean_vin(value):
    """Normaliza e valida um VIN lido da sessao; devolve None se for inutil."""
    vin = (value or "").strip().upper()
    if len(vin) < 12 or not vin:
        return None
    if vin in DUMMY_VINS or "?" in vin:
        return None
    if not re.match(r"^[A-HJ-NPR-Z0-9]{12,}$", vin):
        return None
    return vin


def vin_prefixes(vin, min_len=6):
    """Prefixos utilizaveis para casar um VIN, do mais especifico ao mais curto."""
    if not vin:
        return []
    return [vin[:n] for n in range(len(vin), min_len - 1, -1)]


def _unescape(value):
    return (value.replace("&lt;", "<").replace("&gt;", ">")
                 .replace("&quot;", '"').replace("&apos;", "'")
                 .replace("&amp;", "&"))


def _attrs(pattern, blob):
    return {k: _unescape(v) for k, v in pattern.findall(blob)}


def model_key(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def display_name(stem):
    return stem.replace("_", " ").strip()


def classify(stem):
    """Devolve (familia, ano_modelo, motor) a partir do nome do ficheiro."""
    family = stem.split("_")[0].strip()
    match = RE_MY.search(stem)
    year = "MY" + match.group(1) if match else ""
    engine = ""
    tail = stem.split("_")[-1]
    if re.search(r"\d{3,4}", tail):
        engine = tail
    return family, year, engine


def clean_desc(value):
    return RE_DESC_NOISE.sub("", value).strip()


def parse_session(path, stem):
    """Le um XML decifrado. Tolerante a XML malformado (usa regex)."""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()

    created = RE_CREATED.search(text)
    vins = sorted({v for v in (clean_vin(x) for x in RE_VIN.findall(text)) if v})
    starts = [m.start() for m in RE_DEVICE.finditer(text)]
    modules = {}
    dtcs = []

    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        block = text[start:end]
        head = RE_DEVICE.search(block)
        dev_attrs = _attrs(RE_DEV_ATTR, head.group(1)) if head else {}
        module = dev_attrs.get("deviceName", "").strip()
        ecu_variant = dev_attrs.get("ecuVariantName", "").strip()
        if module and module not in SKIP_MODULES:
            modules[module] = ecu_variant

        for match in RE_ERROR.finditer(block):
            attrs = _attrs(RE_ERR_ATTR, match.group(1))
            code = attrs.get("name", "").strip()
            if not code:
                continue
            dtcs.append({
                "code": code,
                "ecu": module,
                "status": attrs.get("status", ""),
                "desc": clean_desc(attrs.get("description", "")),
            })

    return {
        "session": stem,
        "created": created.group(1) if created else "",
        "vins": vins,
        "modules": modules,
        "dtcs": dtcs,
    }


def module_signature(modules):
    return "|".join(sorted(m for m in modules if m not in SKIP_MODULES))


def merge_into(profile, session, trust_vin=True):
    # So sessoes com o modelo no nome (demos) provam a relacao VIN->modelo.
    # VINs de sessoes reais associadas por heuristica ficam apenas como observacao.
    for vin in session.get("vins") or ():
        bucket = "vins" if trust_vin else "observed_vins"
        profile.setdefault(bucket, set()).add(vin)
    for module, variant in session["modules"].items():
        profile["modules"].setdefault(module, set()).add(variant)
    for dtc in session["dtcs"]:
        entry = profile["dtcs"].setdefault(
            dtc["code"], {"desc": "", "ecu": dtc["ecu"], "sessions": 0})
        if not entry["desc"] and dtc["desc"]:
            entry["desc"] = dtc["desc"]
        if dtc["ecu"] and not entry["ecu"]:
            entry["ecu"] = dtc["ecu"]
        entry["sessions"] += 1


def new_profile(stem):
    family, year, engine = classify(stem)
    return {
        "display": display_name(stem),
        "family": family,
        "model_year": year,
        "engine": engine,
        "modules": {},
        "vins": set(),
        "dtcs": {},
        "sessions": [],
    }


def jaccard(left, right):
    lset, rset = set(left), set(right)
    if not lset or not rset:
        return 0.0
    return len(lset & rset) / len(lset | rset)


def decrypt_dir(paths, keys_file):
    """Decifra .buds2/.buds3 para um diretorio temporario (requer pycryptodome)."""
    try:
        from Crypto.Cipher import AES, DES
    except ImportError:
        sys.exit("pycryptodome ausente: instale com 'pip install pycryptodome' "
                 "ou use --xml-dir com sessoes ja decifradas.")

    import hashlib
    import tempfile

    with open(keys_file, encoding="utf-8-sig") as handle:
        keys = [line.strip() for line in handle if line.strip()]
    out_dir = tempfile.mkdtemp(prefix="buds2_dec_")

    def pbe_md5_des(password, salt, data):
        """PBEWithMD5AndDES: PBKDF1-MD5 (1000 iteracoes) + DES-CBC com PKCS#5."""
        digest = hashlib.md5(password.encode("utf-8") + salt).digest()
        for _ in range(999):
            digest = hashlib.md5(digest).digest()
        raw = DES.new(digest[:8], DES.MODE_CBC, digest[8:16]).decrypt(data)
        pad = raw[-1] if raw else 0
        if 1 <= pad <= 8 and raw[-pad:] == bytes([pad]) * pad:
            raw = raw[:-pad]      # descarta o padding: o resto e a chave AES
        return raw

    written = []
    for path in paths:
        with open(path, "rb") as handle:
            data = handle.read()
        if len(data) < 25:
            continue
        pbe_iv = data[0:8]
        enc_iv = data[8:24]
        key_len = data[24]
        enc_key = data[25:25 + key_len]
        payload = data[25 + key_len:]
        for key in keys:
            try:
                aes_key = pbe_md5_des(key, pbe_iv, enc_key)
            except ValueError:
                continue
            plain = AES.new(aes_key, AES.MODE_CFB, enc_iv,
                            segment_size=8).decrypt(payload)
            if not plain.lstrip().startswith(b"<?xml"):
                continue
            pad = plain[-1] if plain else 0
            if 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad:
                plain = plain[:-pad]
            target = os.path.join(out_dir, os.path.basename(path) + ".xml")
            with open(target, "wb") as handle:
                handle.write(plain)
            written.append(target)
            break
        else:
            print("  ! nao decifrado: %s" % os.path.basename(path))
    return written


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xml-dir", action="append", default=[],
                        help="pasta com XML ja decifrado (pode repetir)")
    parser.add_argument("--buds2-dir", action="append", default=[],
                        help="pasta com .buds2/.buds3 para decifrar")
    parser.add_argument("--keys-file",
                        help="uma palavra-passe candidata por linha")
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    files = []
    for directory in args.xml_dir:
        for name in sorted(os.listdir(directory)):
            if name.lower().endswith(".xml"):
                files.append(os.path.join(directory, name))

    if args.buds2_dir:
        if not args.keys_file:
            sys.exit("--buds2-dir requer --keys-file")
        buds2 = []
        for directory in args.buds2_dir:
            for name in sorted(os.listdir(directory)):
                if name.lower().endswith((".buds2", ".buds3")):
                    buds2.append(os.path.join(directory, name))
        files.extend(decrypt_dir(buds2, args.keys_file))

    if not files:
        sys.exit("nenhum ficheiro de entrada")

    sessions = []
    for path in files:
        stem = os.path.basename(path)
        for suffix in (".buds2.xml", ".buds3.xml", ".xml"):
            if stem.lower().endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        sessions.append(parse_session(path, stem))

    def is_model_named(stem):
        """Nome de modelo (demo) vs. VIN ou timestamp (sessao real)."""
        return not (RE_VIN_STEM.match(stem) or RE_TIMESTAMP_STEM.match(stem))

    # perfis nomeados: so os ficheiros demo trazem o modelo no nome
    named = [s for s in sessions if is_model_named(s["session"])]
    unnamed = [s for s in sessions if not is_model_named(s["session"])]

    models = {}
    for session in named:
        key = model_key(session["session"])
        profile = models.setdefault(key, new_profile(session["session"]))
        profile["sessions"].append(session["session"])
        merge_into(profile, session)

    # sessoes reais (VIN) associadas ao modelo com ECUs mais parecidos
    unmatched = []
    for session in unnamed:
        best_key, best_score = None, 0.0
        for key, profile in models.items():
            score = jaccard(session["modules"], profile["modules"])
            if score > best_score:
                best_key, best_score = key, score
        if best_key and best_score >= 0.6:
            models[best_key]["sessions"].append(session["session"])
            merge_into(models[best_key], session, trust_vin=False)
        else:
            unmatched.append(session)

    payload_models = {}
    signatures = {}
    vin_index = {}
    for key, profile in sorted(models.items()):
        sig = module_signature(profile["modules"])
        signatures.setdefault(sig, []).append(key)
        vins = sorted(profile.get("vins") or ())
        for vin in vins:
            for prefix in vin_prefixes(vin):
                vin_index.setdefault(prefix, set()).add(key)
        payload_models[key] = {
            "display": profile["display"],
            "family": profile["family"],
            "model_year": profile["model_year"],
            "engine": profile["engine"],
            "modules": sorted(profile["modules"]),
            "ecu_variants": sorted(v for vs in profile["modules"].values() for v in vs if v),
            "module_signature": sig,
            "vins": vins,
            "observed_vins": sorted(profile.get("observed_vins") or ()),
            "sessions": len(profile["sessions"]),
            "dtc_count": len(profile["dtcs"]),
            "dtcs": {code: {"desc": e["desc"], "ecu": e["ecu"], "sessions": e["sessions"]}
                     for code, e in sorted(profile["dtcs"].items())},
        }

    payload_unmatched = []
    for session in unmatched:
        payload_unmatched.append({
            "session": session["session"],
            "created": session["created"],
            "modules": sorted(session["modules"]),
            "dtc_count": len(session["dtcs"]),
            "dtcs": {d["code"]: {"desc": d["desc"], "ecu": d["ecu"]}
                     for d in session["dtcs"]},
        })

    payload = {
        "schema": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "BUDS2 .buds2/.buds3 decifrados",
        "model_count": len(payload_models),
        "models": payload_models,
        "module_signatures": signatures,
        "vin_index": {p: sorted(keys) for p, keys in sorted(vin_index.items())},
        "unmatched_sessions": payload_unmatched,
    }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)

    total_dtcs = sum(m["dtc_count"] for m in payload_models.values())
    print("modelos: %d" % len(payload_models))
    print("sessoes nomeadas: %d | sessoes VIN: %d (associadas: %d, sem modelo: %d)"
          % (len(named), len(unnamed), len(unnamed) - len(unmatched), len(unmatched)))
    print("entradas DTC por modelo: %d" % total_dtcs)
    print("escrito: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
