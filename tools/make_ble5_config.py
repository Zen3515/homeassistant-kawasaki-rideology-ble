#!/usr/bin/env python3
"""Generate a kawi_ble5_client config JSON from Rideology support flags.

Usage:
  python3 make_ble5_config.py \
    --info-config 4020F640000511FC77D417FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF \
    --tuning-config 4716FC4700051260FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF \
    --common-service-config 1D0CFA1D00FFFFFFFFFFFFFFFFFFFF \
    --model "Kawasaki-ER500F" \
    --out z500_er500f_config.json

Inputs accept either HEX or Base64 strings. HEX is expected from the API.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from typing import Any, Dict, Tuple

HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

INFO_CONFIG_LAYOUT: tuple[tuple[str, int, int, int], ...] = (
    ("total_distance_traveled", 7, 0xC0, 6),
    ("total_fuel_consumed", 7, 0x30, 4),
    ("engine_fuel_rate", 7, 0x0C, 2),
    ("ecu_battery12V", 7, 0x03, 0),
    ("engine_water_temperature", 8, 0xC0, 6),
    ("engine_oil_temperature", 8, 0x30, 4),
    ("inlet_air_temperature", 8, 0x0C, 2),
    ("boost_temperature", 8, 0x03, 0),
    ("boost_pressure", 9, 0xC0, 6),
    ("fuel_injection", 9, 0x30, 4),
    ("wheel_speed", 9, 0x0C, 2),
    ("engine_speed", 9, 0x03, 0),
    ("gear_position", 10, 0xF0, 4),
    ("throttle_position", 10, 0x0C, 2),
    ("acceleration", 10, 0x03, 0),
    ("lean_angle", 11, 0xC0, 6),
    ("wheelie_flag", 11, 0x30, 4),
    ("wheelie_angle", 11, 0x0C, 2),
    ("tcs_level_hb", 11, 0x03, 0),
    ("tcs_level_lb", 12, 0xC0, 6),
    ("rider_torque_request", 12, 0x30, 4),
    ("engine_torque_request", 12, 0x0C, 2),
    ("engine_torque_actual", 12, 0x03, 0),
    ("odometer", 27, 0xC0, 6),
    ("fuel_gauge", 27, 0x30, 4),
    ("average_fuel_mileage", 27, 0x0C, 2),
    ("meter_battery12V", 27, 0x03, 0),
    ("tripA", 28, 0xC0, 6),
    ("tripB", 28, 0x30, 4),
    ("average_speed", 28, 0x0C, 2),
    ("outer_air_temperature", 28, 0x03, 0),
    ("range_symbol", 29, 0xC0, 6),
    ("range", 29, 0x30, 4),
    ("fuel_consumption", 29, 0x0C, 2),
    ("total_time", 29, 0x03, 0),
    ("instant_fuel_consumption", 31, 0x0C, 2),
)


def _decode_blob(value: str) -> bytes:
    value = value.strip()
    if value.startswith("0x") or value.startswith("0X"):
        value = value[2:]
    if HEX_RE.match(value) and len(value) % 2 == 0:
        return bytes.fromhex(value)
    try:
        return base64.b64decode(value)
    except Exception as exc:  # pragma: no cover
        raise ValueError("Input must be hex or base64") from exc


def _bits(val: int, mask: int, shift: int) -> int:
    return (val & mask) >> shift


def parse_info_config(blob: bytes) -> Dict[str, int]:
    if len(blob) < 35:
        raise ValueError("info_config is too short")
    flags: Dict[str, int] = {}
    for name, index, mask, shift in INFO_CONFIG_LAYOUT:
        flags[name] = _bits(blob[index], mask, shift)
    return flags


def summarize_info_config(blob: bytes, flags: Dict[str, int]) -> Dict[str, Any]:
    """Summarize support and validity semantics from info_config."""

    def _group_ready(a_idx: int, b_idx: int, flag_idx: int) -> bool:
        a_raw = blob[a_idx] & 0xFF
        b_raw = blob[b_idx] & 0xFF
        flag = blob[flag_idx] & 0xFF
        return ((a_raw != 0xFF or b_raw != 0xFF) and ((flag & 0x01) == 0))

    config_retry_required = (
        _group_ready(5, 6, 14) or _group_ready(15, 16, 24) or _group_ready(25, 26, 34)
    )
    names = [name for name, _, _, _ in INFO_CONFIG_LAYOUT]
    supported = [name for name in names if flags.get(name, 3) in (0, 1)]
    unsupported = [name for name in names if flags.get(name, 3) == 3]
    return {
        "config_valid": not config_retry_required,
        "config_retry_required": config_retry_required,
        "supported_count": len(supported),
        "unsupported_count": len(unsupported),
        "supported_fields": supported,
        "unsupported_fields": unsupported,
    }


def parse_tuning_config(blob: bytes) -> Dict[str, int]:
    if len(blob) < 21:
        raise ValueError("tuning_config is too short")
    b = blob
    flags = {}
    flags["tuning_capability_fiEcu"] = _bits(b[7], 0x30, 4)
    b8 = b[8]
    flags["ktrc"] = _bits(b8, 0xC0, 6)
    flags["riding_mode"] = _bits(b8, 0x30, 4)
    flags["kqs"] = _bits(b8, 0x0C, 2)
    flags["kebc"] = _bits(b8, 0x03, 0)
    flags["power"] = _bits(b[9], 0xC0, 6)
    flags["tuning_capability_meter"] = _bits(b[17], 0xC0, 6)
    b19 = b[19]
    flags["kecs_preload_mode"] = _bits(b19, 0x30, 4)
    flags["kecs_mode"] = _bits(b19, 0x0C, 2)
    flags["kecs_load_adjustment"] = _bits(b19, 0x03, 0)
    b20 = b[20]
    flags["kecs_damping_frCom"] = _bits(b20, 0xC0, 6)
    flags["kecs_damping_frTen"] = _bits(b20, 0x30, 4)
    flags["kecs_damping_rrCom"] = _bits(b20, 0x0C, 2)
    flags["kecs_damping_rrTen"] = _bits(b20, 0x03, 0)
    return flags


def parse_common_service_config(blob: bytes) -> Dict[str, int]:
    if len(blob) < 13:
        raise ValueError("common_service_config is too short")
    b = blob
    flags = {}
    b7 = b[7]
    flags["kawasaki_service_setting_capability"] = _bits(b7, 0xC0, 6)
    flags["user_setting_capability"] = _bits(b7, 0x30, 4)
    flags["oil_change_setting_capability"] = _bits(b7, 0x0C, 2)

    b8 = b[8]
    flags["kawasaki_service_notify"] = _bits(b8, 0xC0, 6)
    flags["kawasaki_service_month"] = _bits(b8, 0x30, 4)
    flags["kawasaki_service_day"] = _bits(b8, 0x0C, 2)
    flags["kawasaki_service_year"] = _bits(b8, 0x03, 0)

    b9 = b[9]
    flags["kawasaki_service_distance"] = _bits(b9, 0x30, 4)
    flags["user_setting_notify"] = _bits(b9, 0x0C, 2)
    flags["user_setting_month"] = _bits(b9, 0x03, 0)

    b10 = b[10]
    flags["user_setting_day"] = _bits(b10, 0xC0, 6)
    flags["user_setting_year"] = _bits(b10, 0x30, 4)
    flags["user_setting_distance"] = _bits(b10, 0x03, 0)

    b11 = b[11]
    flags["oil_change_notify"] = _bits(b11, 0xC0, 6)
    flags["oil_change_month"] = _bits(b11, 0x30, 4)
    flags["oil_change_day"] = _bits(b11, 0x0C, 2)
    flags["oil_change_year"] = _bits(b11, 0x03, 0)

    flags["oil_change_distance"] = _bits(b[12], 0x30, 4)
    return flags


def derive_ble5_telemetry_settings(info_flags: Dict[str, int]) -> Tuple[Dict[str, str], Dict[str, bool]]:
    def mode_from_flag(flag: int, a: str, b: str) -> str:
        if flag == 0:
            return a
        if flag == 1:
            return b
        return "auto"

    settings = {
        "rpm_mode": mode_from_flag(info_flags.get("engine_speed", 3), "raw", "quarter"),
        "wheel_mode": mode_from_flag(info_flags.get("wheel_speed", 3), "scaled", "raw1"),
        "throttle_mode": mode_from_flag(info_flags.get("throttle_position", 3), "rider", "mecha"),
        "status_fuel_injection_mode": mode_from_flag(info_flags.get("fuel_injection", 3), "scale_a", "scale_b"),
        "accel_mode": mode_from_flag(info_flags.get("acceleration", 3), "minus2", "raw"),
        "lean_mode": mode_from_flag(info_flags.get("lean_angle", 3), "minus100", "raw"),
        "wheelie_angle_mode": mode_from_flag(info_flags.get("wheelie_angle", 3), "scale09765625", "scale0.1"),
        "rider_torque_mode": mode_from_flag(info_flags.get("rider_torque_request", 3), "scaled", "raw"),
        "engine_torque_request_mode": mode_from_flag(info_flags.get("engine_torque_request", 3), "scaled", "raw"),
        "engine_torque_actual_mode": mode_from_flag(info_flags.get("engine_torque_actual", 3), "scaled", "raw"),
    }

    supported = {
        "status_fuel_injection": info_flags.get("fuel_injection", 3) in (0, 1),
        "wheel_kph": info_flags.get("wheel_speed", 3) in (0, 1),
        "rpm": info_flags.get("engine_speed", 3) in (0, 1),
        "gear": info_flags.get("gear_position", 3) in (0, 1),
        "throttle": info_flags.get("throttle_position", 3) in (0, 1),
        "ecu_battery12V": info_flags.get("ecu_battery12V", 3) == 0,
        "meter_battery12V": info_flags.get("meter_battery12V", 3) == 0,
        "total_fuel_consumed": info_flags.get("total_fuel_consumed", 3) == 0,
        "fuel_gauge": info_flags.get("fuel_gauge", 3) == 0,
        "average_fuel_mileage": info_flags.get("average_fuel_mileage", 3) == 0,
        "tripA": info_flags.get("tripA", 3) == 0,
        "tripB": info_flags.get("tripB", 3) == 0,
        "average_speed": info_flags.get("average_speed", 3) == 0,
        "outer_air_temperature": info_flags.get("outer_air_temperature", 3) == 0,
        "range_symbol": info_flags.get("range_symbol", 3) == 0,
        "range": info_flags.get("range", 3) == 0,
        "fuel_consumption": info_flags.get("fuel_consumption", 3) == 0,
        "total_time": info_flags.get("total_time", 3) == 0,
        "odometer": info_flags.get("odometer", 3) == 0,
        "total_distance_traveled": info_flags.get("total_distance_traveled", 3) == 0,
        "engine_fuel_rate": info_flags.get("engine_fuel_rate", 3) == 0,
        "water_temperature": info_flags.get("engine_water_temperature", 3) == 1,
        "oil_temperature": info_flags.get("engine_oil_temperature", 3) == 1,
        "inlet_air_temperature": info_flags.get("inlet_air_temperature", 3) == 1,
        "instant_fuel_consumption": info_flags.get("instant_fuel_consumption", 3) == 0,
        "accel_g": info_flags.get("acceleration", 3) in (0, 1),
        "lean_deg": info_flags.get("lean_angle", 3) in (0, 1),
        "wheelie_flag": info_flags.get("wheelie_flag", 3) == 0,
        "wheelie_angle": info_flags.get("wheelie_angle", 3) in (0, 1),
        "tcs_level_hb": info_flags.get("tcs_level_hb", 3) == 0,
        "tcs_level_lb": info_flags.get("tcs_level_lb", 3) == 0,
        "rider_torque_request": info_flags.get("rider_torque_request", 3) in (0, 1),
        "engine_torque_request": info_flags.get("engine_torque_request", 3) in (0, 1),
        "engine_torque_actual": info_flags.get("engine_torque_actual", 3) in (0, 1),
        # Keep them explicitly disabled unless a model-specific config overrides it.
        "tire_pressure_fr": False,
        "tire_pressure_rr": False,
        "air_pressure_drop_fr": False,
        "air_pressure_drop_rr": False,
        "low_battery_voltage_fr": False,
        "low_battery_voltage_rr": False,
    }

    return settings, supported


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate kawi_ble5_client config JSON from support flags")
    parser.add_argument("--info-config", required=True, help="info_config (hex or base64)")
    parser.add_argument("--tuning-config", help="tuning_config (hex or base64)")
    parser.add_argument("--common-service-config", help="common_service_config (hex or base64)")
    parser.add_argument("--vehicle-id", help="Vehicle ID string")
    parser.add_argument("--model", help="Model display name")
    parser.add_argument("--out", required=True, help="Output JSON file")
    args = parser.parse_args()

    info_blob = _decode_blob(args.info_config)
    info_flags = parse_info_config(info_blob)
    info_summary = summarize_info_config(info_blob, info_flags)
    ble5_settings, supported = derive_ble5_telemetry_settings(info_flags)

    tuning_flags = None
    if args.tuning_config:
        tuning_flags = parse_tuning_config(_decode_blob(args.tuning_config))

    common_flags = None
    if args.common_service_config:
        common_flags = parse_common_service_config(_decode_blob(args.common_service_config))

    payload = {
        # "vehicle_id": args.vehicle_id,
        "model": args.model,
        "info_config_hex": args.info_config,
        "tuning_config_hex": args.tuning_config,
        "common_service_config_hex": args.common_service_config,
        "info_config_flags": info_flags,
        "info_config_summary": info_summary,
        "tuning_config_flags": tuning_flags,
        "common_service_config_flags": common_flags,
        "ble5_telemetry": {
            **ble5_settings,
            "supported_fields": supported,
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
