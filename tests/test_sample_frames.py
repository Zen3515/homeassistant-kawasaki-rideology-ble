"""Regression tests for observed Rideology BLE5 sample frames."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


def _install_bleak_stubs() -> None:
    """Install minimal stubs so parser module can be imported without BLE deps."""
    bleak = types.ModuleType("bleak")

    class BleakClient:  # pragma: no cover - import stub
        pass

    class BleakError(Exception):  # pragma: no cover - import stub
        pass

    bleak.BleakClient = BleakClient
    bleak.BleakError = BleakError
    sys.modules["bleak"] = bleak

    backends = types.ModuleType("bleak.backends")
    sys.modules["bleak.backends"] = backends

    characteristic = types.ModuleType("bleak.backends.characteristic")

    class BleakGATTCharacteristic:  # pragma: no cover - import stub
        pass

    characteristic.BleakGATTCharacteristic = BleakGATTCharacteristic
    sys.modules["bleak.backends.characteristic"] = characteristic

    device = types.ModuleType("bleak.backends.device")

    class BLEDevice:  # pragma: no cover - import stub
        pass

    device.BLEDevice = BLEDevice
    sys.modules["bleak.backends.device"] = device

    retry = types.ModuleType("bleak_retry_connector")

    async def establish_connection(*_args, **_kwargs):  # pragma: no cover - import stub
        raise RuntimeError("BLE connection is not available in parser tests")

    retry.establish_connection = establish_connection
    sys.modules["bleak_retry_connector"] = retry


def _load_parser_module():
    _install_bleak_stubs()
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "custom_components" / "kawasaki" / "kawi_ble5_client.py"
    spec = importlib.util.spec_from_file_location("kawi_ble5_client_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hx(value: str) -> bytes:
    return bytes.fromhex(value)


class TestSampleFrames(unittest.TestCase):
    """Parser regression coverage for observed on-bike sample frames."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_parser_module()
        cls.sample = {
            "03": "03207a030002714d4c35455235303002724641444135353535027338ffffffffffffff",
            "08": "080c00ffff0a08017803e800c80064",
            "0B": "0b2000ffff0501486f6d654173736905027374616e7400000000000000000000000000",
            "1A": "1a0c7e1a00ffffffffffffffffffff",
            "1B": "1b0c894800ffffffffffffffffffff",
            "1D": "1d0c801d00ffffffffffffffffffff",
            "1E": "1e2a911e01ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "20_a": "200c871b00050a00ffffffffffffff",
            "20_b": "200c9208000a08017803e800c80064",
            "20_c": "2020830b000501486f6d654173736905027374616e7400000000000000000000000000",
            "20_d": "202a8a4800050900ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "20_e": "202a8d1e01050c00ffffffffffffff050d00ffffffffffffff050e00ffffffffffffffffffffffffffffffffff",
            "20_f": "2002790300",
            "20_g": "20027b4000",
            "20_h": "20027d1a00",
            "20_i": "20027f1d00",
            "20_j": "2002814700",
            "20_k": "2002854100",
            "20_l": "2002934500",
            "20_m": "20029b4201",
            "30_a": "300c88ffff050a00ffffffffffffff",
            "30_b": "300c8bffff050900ffffffffffffff",
            "30_c": "300c8effff050c00ffffffffffffff",
            "30_d": "300c8fffff050d00ffffffffffffff",
            "30_e": "300c90ffff050e00ffffffffffffff",
            "30_f": "302084ffff0501486f6d654173736905027374616e74000000ffffffffffffffffffff",
            "40": "40207c40000511fc77d417ffffffffffffffffffffffffffffffffffffffffffffffff",
            "41": "41528641000514000000000000009effffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "42": "420001",
            "42_b": "420c804200ffffffffffffffffffff",
            "45_a": "4534a4ffffffffffffffffffffffff05175000004c00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "45_b": "4534b4ffffffffffffffffffffffff05175000004c00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "45_c": "4534c4ffffffffffffffffffffffff05175000004c00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "45_d": "4534d4ffffffffffffffffffffffff05175000004c00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "45_e": "4534e4ffffffffffffffffffffffff05175000004c00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "47": "4716824700051260ffffffffffffffffffffffffffffffffff",
            "48": "48168c4800ffffffffffffffffffffffffffffffffffffffff",
            "4B_1": "4b2a94ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_2": "4b2a95ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_3": "4b2a97ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_4": "4b2a98ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_5": "4b2a9affffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_6": "4b2a9cffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_7": "4b2a9effffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_8": "4b2a9fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_9": "4b2aa1ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_10": "4b2aa2ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_11": "4b2aa5ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "4B_12": "4b2aa6ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        }

    def test_model_info_frame_03(self) -> None:
        parsed = self.mod.parse_model_info(_hx(self.sample["03"]))
        self.assertEqual(parsed["frame"], "0x03")
        self.assertEqual(parsed["model_name"], "ML5ER500")
        self.assertEqual(parsed["vin"], "ML5ER500FADA55558")
        self.assertEqual(parsed["vin_part_71"], "ML5ER500")
        self.assertEqual(parsed["vin_part_72"], "FADA5555")
        self.assertEqual(parsed["vin_part_73"], "8")

    def test_frames_1a_1b_1d_1e_chain(self) -> None:
        frame_1a = self.mod.parse_general_setting_capability(_hx(self.sample["1A"]))
        self.assertTrue(frame_1a["config_valid"])
        self.assertFalse(frame_1a["config_retry_required"])
        self.assertFalse(frame_1a["shift_lamp_level_supported"])
        self.assertFalse(frame_1a["supports_day_setting"])
        self.assertEqual(frame_1a["navi_control_point_capability"], 15)

        frame_1b = self.mod.parse_general_settings(_hx(self.sample["1B"]), frame_1a)
        self.assertEqual(frame_1b["frame"], "0x1B")
        self.assertEqual(frame_1b["related_command"], 0x48)
        self.assertIsNone(frame_1b["result_code"])
        self.assertIsNone(frame_1b["day"])
        self.assertIsNone(frame_1b["shift_lamp_level"])

        frame_1d = self.mod.parse_common_service_config_flags(_hx(self.sample["1D"]))
        self.assertTrue(frame_1d["config_valid"])
        self.assertEqual(frame_1d["supported_count"], 0)
        self.assertEqual(frame_1d["unsupported_count"], 18)
        self.assertFalse(frame_1d["kawasaki_service_supported"])
        self.assertFalse(frame_1d["rider_setting_supported"])
        self.assertFalse(frame_1d["oil_change_supported"])

        common_flags = {
            name: value
            for name, _, _, _ in self.mod._COMMON_SERVICE_CONFIG_FIELD_LAYOUT
            if isinstance((value := frame_1d.get(name)), int)
        }
        frame_1e = self.mod.parse_service_indicator(
            _hx(self.sample["1E"]),
            {"common_service_config_flags": {}},
            common_flags,
        )
        self.assertEqual(frame_1e["frame"], "0x1E")
        self.assertFalse(frame_1e["kawasaki_service_supported"])
        self.assertFalse(frame_1e["rider_setting_supported"])
        self.assertFalse(frame_1e["oil_change_supported"])
        self.assertIsNone(frame_1e["kawasaki_service_notify"])
        self.assertIsNone(frame_1e["oil_change_distance"])

    def test_ack_frames_20(self) -> None:
        expected = {
            "20_a": (0x1B, "accepted"),
            "20_b": (0x08, "rejected_or_unsupported"),
            "20_c": (0x0B, "error_0x48"),
            "20_d": (0x48, "accepted"),
            "20_e": (0x1E, "accepted"),
            "20_f": (0x03, "accepted"),
            "20_g": (0x40, "accepted"),
            "20_h": (0x1A, "accepted"),
            "20_i": (0x1D, "accepted"),
            "20_j": (0x47, "accepted"),
            "20_k": (0x41, "accepted"),
            "20_l": (0x45, "accepted"),
            "20_m": (0x42, "rejected_or_unsupported"),
        }
        for key, (ack_command, result_text) in expected.items():
            with self.subTest(frame=key):
                parsed = self.mod.parse_ack(_hx(self.sample[key]))
                self.assertEqual(parsed["frame"], "0x20")
                self.assertEqual(parsed["ack_command"], ack_command)
                self.assertEqual(parsed["result_text"], result_text)
                if key == "20_b":
                    self.assertEqual(parsed["meter_indication_block_id"], 0x0A)
                    self.assertEqual(parsed["meter_indication_command_id"], 0x08)
                    self.assertEqual(parsed["meter_indication_param_1"], 120)
                    self.assertEqual(parsed["meter_indication_param_2"], 1000)
                    self.assertEqual(parsed["meter_indication_param_3"], 200)
                    self.assertEqual(parsed["meter_indication_param_4"], 100)
                if key == "20_c":
                    self.assertEqual(parsed["phone_model_text"], "HomeAssistant")
                    self.assertEqual(parsed["phone_model_chunk_ids"], "0x01,0x02")

    def test_phone_model_frame_0b(self) -> None:
        parsed = self.mod.parse_phone_model(_hx(self.sample["0B"]))
        self.assertEqual(parsed["frame"], "0x0B")
        self.assertEqual(parsed["payload_len"], 0x20)
        self.assertEqual(parsed["text"], "HomeAssistant")
        self.assertEqual(parsed["chunk_ids"], "0x01,0x02")

    def test_meter_indication_init_frame_08(self) -> None:
        parsed = self.mod.parse_meter_indication_init(_hx(self.sample["08"]))
        self.assertEqual(parsed["frame"], "0x08")
        self.assertEqual(parsed["payload_len"], 0x0C)
        self.assertEqual(parsed["block_id"], 0x0A)
        self.assertEqual(parsed["command_id"], 0x08)
        self.assertTrue(parsed["enabled"])
        self.assertEqual(parsed["param_1"], 120)
        self.assertEqual(parsed["param_2"], 1000)
        self.assertEqual(parsed["param_3"], 200)
        self.assertEqual(parsed["param_4"], 100)
        self.assertTrue(parsed["is_default_profile"])

    def test_emc_info_frame_42_short_request_like(self) -> None:
        parsed = self.mod.parse_emc_info(_hx(self.sample["42"]))
        self.assertEqual(parsed["frame"], "0x42")
        self.assertEqual(parsed["raw_len"], 3)
        self.assertEqual(parsed["packet_type"], "request_command")
        self.assertEqual(parsed["request_tail"], 0x01)

    def test_emc_info_frame_42_service_config_like(self) -> None:
        parsed = self.mod.parse_emc_info(_hx(self.sample["42_b"]))
        self.assertEqual(parsed["frame"], "0x42")
        self.assertEqual(parsed["packet_type"], "service_indicator_config_like")
        self.assertTrue(parsed["config_valid"])
        self.assertFalse(parsed["kawasaki_service_supported"])
        self.assertFalse(parsed["rider_setting_supported"])
        self.assertFalse(parsed["oil_change_supported"])
        self.assertEqual(parsed["supported_count"], 0)
        self.assertEqual(parsed["unsupported_count"], 18)

    def test_status_frames_30(self) -> None:
        for key, block_id in (
            ("30_a", 0x0A),
            ("30_b", 0x09),
            ("30_c", 0x0C),
            ("30_d", 0x0D),
            ("30_e", 0x0E),
        ):
            with self.subTest(frame=key):
                parsed = self.mod.parse_status_report(_hx(self.sample[key]))
                self.assertEqual(parsed["frame"], "0x30")
                self.assertEqual(parsed["status_type"], "block_result")
                self.assertEqual(parsed["block_id"], block_id)
                self.assertEqual(parsed["result_code"], 0x00)
                self.assertEqual(parsed["result_text"], "accepted")

        parsed_text = self.mod.parse_status_report(_hx(self.sample["30_f"]))
        self.assertEqual(parsed_text["status_type"], "text_chunks")
        self.assertEqual(parsed_text["text"], "HomeAssistant")
        self.assertEqual(parsed_text["chunk_ids"], "0x01,0x02")

    def test_config_and_data_frames_40_41_45_47_48_4b(self) -> None:
        frame_40 = self.mod.parse_info_config_flags(_hx(self.sample["40"]))
        self.assertTrue(frame_40["config_valid"])
        self.assertEqual(frame_40["supported_count"], 8)
        self.assertEqual(frame_40["unsupported_count"], 28)
        self.assertIn("ecu_battery12V", frame_40["supported_fields"])
        self.assertIn("inlet_air_temperature", frame_40["supported_fields"])

        info_flags = {
            name: value
            for name, _, _, _ in self.mod._INFO_CONFIG_FIELD_LAYOUT
            if isinstance((value := frame_40.get(name)), int)
        }
        tuning_flags = self.mod.parse_tuning_config_flags(_hx(self.sample["47"]))
        self.assertEqual(tuning_flags["supported_count"], 0)
        self.assertEqual(tuning_flags["unsupported_count"], 14)
        self.assertEqual(tuning_flags["tuning_capability_fiEcu"], 2)

        tuning_flag_values = {
            name: value
            for name, _, _, _ in self.mod._TUNING_CONFIG_FIELD_LAYOUT
            if isinstance((value := tuning_flags.get(name)), int)
        }

        cfg = {
            "supported_fields": {
                "ecu_battery12V": True,
                "meter_battery12V": False,
                "odometer": False,
                "fuel_gauge": False,
                "water_temperature": True,
                "oil_temperature": False,
                "inlet_air_temperature": True,
                "tire_pressure_fr": False,
                "tire_pressure_rr": False,
                "rr_suspension_stroke": False,
                "fr_suspension_stroke": False,
                "rr_suspension_stroke_vp": False,
                "fr_suspension_stroke_vp": False,
                "ay_psip1": False,
                "ay": False,
                "ax_psip3": False,
                "ax": False,
                "az_psip2": False,
                "az": False,
            },
            "info_config_flags": info_flags,
            "tuning_config_flags": tuning_flag_values,
        }

        frame_41 = self.mod.parse_mc_info(_hx(self.sample["41"]), cfg, info_flags)
        self.assertEqual(frame_41["frame"], "0x41")
        self.assertAlmostEqual(frame_41["ecu_battery12V"], 12.34375)
        self.assertIsNone(frame_41["meter_battery12V"])
        self.assertIsNone(frame_41["odometer"])

        for key in ("45_a", "45_b", "45_c", "45_d", "45_e"):
            with self.subTest(frame=key):
                frame_45 = self.mod.parse_riding_log_ext(_hx(self.sample[key]), cfg, info_flags)
                self.assertEqual(frame_45["frame"], "0x45")
                self.assertEqual(frame_45["water_temperature"], 40)
                self.assertEqual(frame_45["inlet_air_temperature"], 36)
                self.assertIsNone(frame_45["odometer"])
                self.assertIsNone(frame_45["tire_pressure_fr"])

        frame_48 = self.mod.parse_vehicle_settings(
            _hx(self.sample["48"]),
            {"tuning_config_flags": tuning_flag_values},
            tuning_flag_values,
        )
        self.assertEqual(frame_48["frame"], "0x48")
        self.assertEqual(frame_48["decoded_count"], 0)
        self.assertIsNone(frame_48["decoded_fields"])
        self.assertIsNone(frame_48["ktrc"])

        for key in (
            "4B_1",
            "4B_2",
            "4B_3",
            "4B_4",
            "4B_5",
            "4B_6",
            "4B_7",
            "4B_8",
            "4B_9",
            "4B_10",
            "4B_11",
            "4B_12",
        ):
            with self.subTest(frame=key):
                frame_4b = self.mod.parse_riding_log_high(_hx(self.sample[key]), cfg)
                self.assertEqual(frame_4b["frame"], "0x4B")
                self.assertIsNone(frame_4b["rr_suspension_stroke"])
                self.assertIsNone(frame_4b["fr_suspension_stroke"])
                self.assertIsNone(frame_4b["ay"])
                self.assertIsNone(frame_4b["az"])


if __name__ == "__main__":
    unittest.main()
