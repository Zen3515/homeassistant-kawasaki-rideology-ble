"""BLE5 client and parsers for Kawasaki Rideology."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from datetime import datetime
import logging
import platform

from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

SERVICE_UUID = "92faec07-c075-4b7c-a6c2-bbd1d1a150f5"
CONTROL_UUID = "acf1b15c-10f9-4942-a32d-f9e019b95402"
NOTIFY_UUIDS = [
    "3aabbb34-eac0-40f5-9d50-3a1ee6787136",
    "02fad1bd-358e-441c-b296-fe874af38a7e",
    "5e119eba-35a7-4463-a7af-7fa40a302350",
]

FRAME_GENERAL_SETTINGS = 0x1B
FRAME_ACK = 0x20
FRAME_MODEL_INFO = 0x03
FRAME_METER_INDICATION_INIT = 0x08
FRAME_OPTIONAL_PROBE_0A = 0x0A
FRAME_PHONE_MODEL = 0x0B
FRAME_GENERAL_SETTING_CAPABILITY = 0x1A
FRAME_MC_INFO_CONFIG = 0x40
FRAME_VEHICLE_SETTING_CONFIG = 0x47
FRAME_MC_INFO = 0x41
FRAME_EMC_INFO = 0x42
FRAME_COMMON_SERVICE = 0x1D
FRAME_SERVICE_INDICATOR = 0x1E
FRAME_RIDING_LOG_EXT = 0x45
FRAME_VEHICLE_SETTINGS = 0x48
FRAME_STATUS_REPORT = 0x30
FRAME_RIDING_LOG_MID = 0x4A
FRAME_RIDING_LOG_HIGH = 0x4B

DEFAULT_STARTUP_FRAMES = (
    FRAME_MODEL_INFO,
    FRAME_MC_INFO_CONFIG,
    FRAME_GENERAL_SETTING_CAPABILITY,
    FRAME_COMMON_SERVICE,
    FRAME_VEHICLE_SETTING_CONFIG,
    FRAME_PHONE_MODEL,
    FRAME_MC_INFO,
    FRAME_GENERAL_SETTINGS,
    FRAME_VEHICLE_SETTINGS,
    FRAME_SERVICE_INDICATOR,
    FRAME_METER_INDICATION_INIT,
    FRAME_RIDING_LOG_EXT,
    FRAME_EMC_INFO,
)

_LOGGER = logging.getLogger(__name__)

_FRAME_NAME_BY_ID: dict[int, str] = {
    FRAME_MODEL_INFO: "model_info",
    FRAME_METER_INDICATION_INIT: "meter_indication_init",
    FRAME_OPTIONAL_PROBE_0A: "optional_probe_0a",
    FRAME_PHONE_MODEL: "phone_model",
    FRAME_GENERAL_SETTING_CAPABILITY: "general_setting_capability",
    FRAME_GENERAL_SETTINGS: "general_settings",
    FRAME_COMMON_SERVICE: "common_service",
    FRAME_SERVICE_INDICATOR: "service_indicator",
    FRAME_STATUS_REPORT: "status_report",
    FRAME_MC_INFO_CONFIG: "mc_info_config",
    FRAME_MC_INFO: "mc_info",
    FRAME_EMC_INFO: "emc_info",
    FRAME_RIDING_LOG_EXT: "riding_log_ext",
    FRAME_VEHICLE_SETTING_CONFIG: "vehicle_setting_config",
    FRAME_VEHICLE_SETTINGS: "vehicle_settings",
    FRAME_RIDING_LOG_MID: "riding_log_mid",
    FRAME_RIDING_LOG_HIGH: "riding_log_high",
}

_INFO_CONFIG_FIELD_LAYOUT: tuple[tuple[str, int, int, int], ...] = (
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

_TUNING_CONFIG_FIELD_LAYOUT: tuple[tuple[str, int, int, int], ...] = (
    ("tuning_capability_fiEcu", 7, 0x30, 4),
    ("ktrc", 8, 0xC0, 6),
    ("riding_mode", 8, 0x30, 4),
    ("kqs", 8, 0x0C, 2),
    ("kebc", 8, 0x03, 0),
    ("power", 9, 0xC0, 6),
    ("tuning_capability_meter", 17, 0xC0, 6),
    ("kecs_preload_mode", 19, 0x30, 4),
    ("kecs_mode", 19, 0x0C, 2),
    ("kecs_load_adjustment", 19, 0x03, 0),
    ("kecs_damping_frCom", 20, 0xC0, 6),
    ("kecs_damping_frTen", 20, 0x30, 4),
    ("kecs_damping_rrCom", 20, 0x0C, 2),
    ("kecs_damping_rrTen", 20, 0x03, 0),
)

_COMMON_SERVICE_CONFIG_FIELD_LAYOUT: tuple[tuple[str, int, int, int], ...] = (
    ("kawasaki_service_setting_capability", 7, 0xC0, 6),
    ("user_setting_capability", 7, 0x30, 4),
    ("oil_change_setting_capability", 7, 0x0C, 2),
    ("kawasaki_service_notify", 8, 0xC0, 6),
    ("kawasaki_service_month", 8, 0x30, 4),
    ("kawasaki_service_day", 8, 0x0C, 2),
    ("kawasaki_service_year", 8, 0x03, 0),
    ("kawasaki_service_distance", 9, 0x30, 4),
    ("user_setting_notify", 9, 0x0C, 2),
    ("user_setting_month", 9, 0x03, 0),
    ("user_setting_day", 10, 0xC0, 6),
    ("user_setting_year", 10, 0x30, 4),
    ("user_setting_distance", 10, 0x03, 0),
    ("oil_change_notify", 11, 0xC0, 6),
    ("oil_change_month", 11, 0x30, 4),
    ("oil_change_day", 11, 0x0C, 2),
    ("oil_change_year", 11, 0x03, 0),
    ("oil_change_distance", 12, 0x30, 4),
)


def _frame_name(frame_id: int | None) -> str:
    """Return a friendly frame label for logs."""
    if not isinstance(frame_id, int):
        return "unknown"
    return _FRAME_NAME_BY_ID.get(frame_id, f"unknown_0x{frame_id:02X}")


def _ack_result_text(result_code: int | None) -> str:
    """Map ACK result byte to a readable status."""
    if result_code is None:
        return "unknown"
    if result_code == 0x00:
        return "accepted"
    if result_code == 0x01:
        return "rejected_or_unsupported"
    return f"error_0x{result_code:02X}"


def _parse_frame_id_list(entries: object) -> list[int]:
    """Normalize frame IDs from config values."""
    if entries is None:
        return []

    values: list[object]
    if isinstance(entries, (int, str)):
        values = [entries]
    elif isinstance(entries, (list, tuple, set)):
        values = list(entries)
    else:
        return []

    resolved: list[int] = []
    for entry in values:
        frame_id: int | None = None
        if isinstance(entry, int):
            frame_id = entry
        elif isinstance(entry, str):
            text = entry.strip().lower()
            if not text:
                continue
            with contextlib.suppress(ValueError):
                frame_id = int(text, 16 if text.startswith("0x") else 10)

        if frame_id is None:
            continue
        frame_id &= 0xFF
        # Preserve order and duplicates because app startup sequences can
        # intentionally repeat frame IDs (for example a trailing 0x42).
        resolved.append(frame_id)
    return resolved


def _parse_frame_profiles(entries: object) -> list[list[int]]:
    """Normalize startup frame profiles from config values."""
    if not isinstance(entries, (list, tuple)):
        return []
    if not entries:
        return []

    # Allow a flat list to behave as a single startup profile.
    if all(isinstance(entry, (int, str)) for entry in entries):
        parsed = _parse_frame_id_list(entries)
        return [parsed] if parsed else []

    profiles: list[list[int]] = []
    for entry in entries:
        parsed = _parse_frame_id_list(entry)
        if parsed:
            profiles.append(parsed)
    return profiles


class KawiBle5Client:
    """Stateful BLE5 client intended for HA integration use."""

    def __init__(
        self,
        *,
        address: str | None = None,
        ble_device: BLEDevice | None = None,
        config: dict | None = None,
        rpm_mode: str | None = None,
        wheel_mode: str | None = None,
        mtu: int = 517,
        log_1b: bool = False,
        debug: bool = False,
        control_write_with_response: bool | None = None,
        on_frame: Callable[[int, dict | None, bytes], None] | None = None,
    ) -> None:
        """Initialize the BLE client."""
        self.address = address
        self.ble_device = ble_device
        self.config = config or {}
        self.rpm_mode = rpm_mode or self.config.get("rpm_mode") or "auto"
        self.wheel_mode = wheel_mode or self.config.get("wheel_mode") or "auto"
        self.mtu = mtu
        self.log_1b = log_1b
        self.debug = debug
        self.log_all_frames = bool(self.config.get("log_all_frames", True))
        self.control_write_with_response = (
            control_write_with_response
            if control_write_with_response is not None
            else bool(self.config.get("control_write_with_response", True))
        )
        self.force_start_notify = bool(self.config.get("force_start_notify", True))
        self.pair_before_startup = bool(self.config.get("pair_before_startup", False))
        self.force_rebond_before_startup = bool(
            self.config.get("force_rebond_before_startup", False)
        )
        self.require_startup_responses = bool(
            self.config.get("require_startup_responses", True)
        )
        self.startup_wait_frames = set(
            _parse_frame_id_list(self.config.get("startup_wait_frames"))
        )
        self.startup_no_wait_frames = set(
            _parse_frame_id_list(self.config.get("startup_no_wait_frames"))
        )
        self.startup_frame_profiles = _parse_frame_profiles(
            self.config.get("startup_frame_profiles")
        )
        self._startup_profile_index = 0
        self.startup_wait_timeout_s = float(
            self.config.get("startup_wait_timeout_s", 3.0)
        )
        self.startup_wait_poll_s = max(
            0.01, float(self.config.get("startup_wait_poll_s", 0.05))
        )
        self.startup_retries = max(0, int(self.config.get("startup_retries", 0)))
        self.startup_retry_delay_s = max(
            0.0, float(self.config.get("startup_retry_delay_s", 0.5))
        )
        self.force_rebond_on_disconnect = bool(
            self.config.get("force_rebond_on_disconnect", False)
        )
        self._max_pending_frames = max(
            32, int(self.config.get("max_pending_frames", 512))
        )
        self._client: BleakClient | None = None
        self._control_target: BleakGATTCharacteristic | str = CONTROL_UUID
        self._notify_targets: list[BleakGATTCharacteristic | str] = list(NOTIFY_UUIDS)
        self._notify_handle_to_uuid: dict[int, str] = {}
        self._pending_frames: list[bytes] = []
        self.last_riding_log: dict | None = None
        self.last_riding_log_ext: dict | None = None
        self.last_riding_log_high: dict | None = None
        self.last_general: dict | None = None
        self.last_general_setting_capability: dict | None = None
        self.last_service_indicator: dict | None = None
        self.last_info_config_flags: dict[str, int] | None = None
        self.last_common_service_config_flags: dict[str, int] | None = None
        self.last_tuning_config_flags: dict[str, int] | None = None
        self.last_vehicle_settings: dict | None = None
        self.last_mc_info: dict | None = None
        self.on_frame = on_frame
        _LOGGER.debug(
            (
                "Client policy for %s: control_write_with_response=%s "
                "require_startup_responses=%s startup_wait_timeout_s=%.2f "
                "startup_wait_frames=%s startup_no_wait_frames=%s startup_profiles=%s force_start_notify=%s "
                "force_rebond_before_startup=%s startup_retries=%s "
                "startup_retry_delay_s=%.2f force_rebond_on_disconnect=%s"
            ),
            self.address or (self.ble_device.address if self.ble_device else "unknown"),
            self.control_write_with_response,
            self.require_startup_responses,
            self.startup_wait_timeout_s,
            sorted(self.startup_wait_frames),
            sorted(self.startup_no_wait_frames),
            len(self.startup_frame_profiles),
            self.force_start_notify,
            self.force_rebond_before_startup,
            self.startup_retries,
            self.startup_retry_delay_s,
            self.force_rebond_on_disconnect,
        )

    @property
    def connected(self) -> bool:
        """Return True if the client is connected."""
        if self._client is None:
            return False
        return bool(self._client.is_connected)

    async def async_start(self) -> None:
        """Connect and start notifications."""
        if self._client is not None and self.connected:
            _LOGGER.debug("Skipping start because client is already connected")
            return

        target = self.ble_device or self.address
        if not target:
            raise RuntimeError("Device not found. Provide address or ble_device.")

        if self.ble_device:
            _LOGGER.debug(
                "Connecting with retry connector to %s",
                self.address or self.ble_device.address,
            )
            self._client = await establish_connection(
                BleakClient,
                self.ble_device,
                self.address or self.ble_device.address,
            )
        else:
            _LOGGER.debug("Connecting directly to %s", self.address)
            self._client = BleakClient(target)
            await self._client.connect()

        _LOGGER.debug("Connected to %s", self.address or self.ble_device)
        rebond_succeeded = False
        if self.force_rebond_before_startup:
            rebond_succeeded = await self.async_force_rebond()

        if self.mtu and hasattr(self._client, "request_mtu"):
            # Not all platforms support MTU negotiation
            with contextlib.suppress(Exception):
                _LOGGER.debug("Requesting MTU %s", self.mtu)
                await self._client.request_mtu(self.mtu)

        should_pair = self.pair_before_startup or rebond_succeeded
        if should_pair:
            if not self.connected:
                _LOGGER.debug("Reconnecting before pair for %s", self.address)
                await self._client.connect()
            await self.async_pair()
            if not self.connected:
                _LOGGER.debug("Reconnecting after pair for %s", self.address)
                await self._client.connect()

        self._resolve_gatt_targets()
        for target in self._notify_targets:
            target_id = (
                target.uuid if isinstance(target, BleakGATTCharacteristic) else target
            )
            _LOGGER.debug("Starting notify on %s", target_id)
            if self.force_start_notify:
                try:
                    await self._client.start_notify(
                        target,
                        self._handle_notify,
                        bluez={"use_start_notify": True},
                    )
                except TypeError:
                    _LOGGER.debug(
                        "Bleak backend does not support bluez use_start_notify; "
                        "falling back to default start_notify"
                    )
                    await self._client.start_notify(target, self._handle_notify)
            else:
                await self._client.start_notify(target, self._handle_notify)
        self._pending_frames.clear()
        _LOGGER.debug("Notifications enabled for %s", self.address or self.ble_device)

    async def async_stop(self) -> None:
        """Stop notifications and disconnect."""
        if not self._client:
            _LOGGER.debug("Skipping stop because client is not connected")
            return
        _LOGGER.debug("Stopping BLE client for %s", self.address or self.ble_device)
        if self.force_rebond_on_disconnect:
            _LOGGER.debug(
                "Force rebond on disconnect enabled; unpairing %s before disconnect",
                self.address or self.ble_device,
            )
            with contextlib.suppress(Exception):
                await self.async_unpair()
        for target in self._notify_targets:
            target_id = (
                target.uuid if isinstance(target, BleakGATTCharacteristic) else target
            )
            with contextlib.suppress(Exception):
                _LOGGER.debug("Stopping notify on %s", target_id)
                await self._client.stop_notify(target)
        try:
            await self._client.disconnect()
        finally:
            _LOGGER.debug(
                "Disconnected BLE client for %s", self.address or self.ble_device
            )
            self._client = None
            self._control_target = CONTROL_UUID
            self._notify_targets = list(NOTIFY_UUIDS)
            self._notify_handle_to_uuid.clear()

    async def async_send(self, data: bytes) -> None:
        """Send a raw frame to the control characteristic."""
        if not self._client or not self.connected:
            raise RuntimeError("Not connected")
        _LOGGER.debug(
            "Sending frame id=0x%02X len=%s",
            data[0],
            len(data),
        )
        if self.debug:
            _LOGGER.debug("Sending raw frame bytes: %s", data.hex())
        response = self.control_write_with_response
        if self.debug:
            _LOGGER.debug("Control write response=%s", response)
        try:
            await self._client.write_gatt_char(
                self._control_target, data, response=response
            )
        except BleakError as exc:
            if "Insufficient authorization" in str(exc):
                _LOGGER.debug(
                    "Write rejected (authorization). Attempting pair then retry."
                )
                await self.async_pair()
                await self._client.write_gatt_char(
                    self._control_target, data, response=response
                )
            else:
                raise

    def _resolve_gatt_targets(self) -> None:
        """Resolve control/notify characteristics in the target service."""
        if not self._client:
            return

        services = getattr(self._client, "services", None)
        if not services:
            _LOGGER.debug(
                "No GATT service cache available; falling back to UUID-only targets"
            )
            return

        service_dict = getattr(services, "services", {})
        service_values = list(service_dict.values())
        if not service_values:
            _LOGGER.debug("Empty GATT service cache; falling back to UUID-only targets")
            return

        target_service = None
        for service in service_values:
            if str(getattr(service, "uuid", "")).lower() == SERVICE_UUID:
                target_service = service
                break

        if target_service is None:
            _LOGGER.warning(
                "Target service %s not found; discovered services=%s",
                SERVICE_UUID,
                ", ".join(
                    str(getattr(service, "uuid", "?")) for service in service_values
                ),
            )
        else:
            _LOGGER.debug(
                "Using target service %s with %s characteristics",
                target_service.uuid,
                len(target_service.characteristics),
            )

        # Build candidates across all services for diagnostics/fallback.
        control_candidates: list[tuple[str, BleakGATTCharacteristic]] = []
        notify_candidates: dict[str, list[tuple[str, BleakGATTCharacteristic]]] = {
            uuid: [] for uuid in NOTIFY_UUIDS
        }
        for service in service_values:
            service_uuid = str(getattr(service, "uuid", ""))
            for characteristic in service.characteristics:
                char_uuid = str(characteristic.uuid)
                if char_uuid == CONTROL_UUID:
                    control_candidates.append((service_uuid, characteristic))
                if char_uuid in notify_candidates:
                    notify_candidates[char_uuid].append((service_uuid, characteristic))

        # Resolve control characteristic with service-scoped preference.
        selected_control: BleakGATTCharacteristic | None = None
        if target_service is not None:
            selected_control = target_service.get_characteristic(CONTROL_UUID)
        if selected_control is None and control_candidates:
            selected_control = control_candidates[0][1]

        if selected_control is not None:
            self._control_target = selected_control
            _LOGGER.debug(
                "Control target resolved uuid=%s handle=%s properties=%s",
                selected_control.uuid,
                getattr(selected_control, "handle", "?"),
                sorted(getattr(selected_control, "properties", [])),
            )
        else:
            _LOGGER.warning(
                "Control characteristic %s not found; using UUID fallback",
                CONTROL_UUID,
            )
            self._control_target = CONTROL_UUID

        # Resolve notify characteristics with service-scoped preference.
        resolved_notifies: list[BleakGATTCharacteristic | str] = []
        self._notify_handle_to_uuid.clear()
        for notify_uuid in NOTIFY_UUIDS:
            selected_notify: BleakGATTCharacteristic | None = None
            if target_service is not None:
                selected_notify = target_service.get_characteristic(notify_uuid)
            if selected_notify is None and notify_candidates[notify_uuid]:
                selected_notify = notify_candidates[notify_uuid][0][1]

            if selected_notify is not None:
                resolved_notifies.append(selected_notify)
                handle = getattr(selected_notify, "handle", None)
                if isinstance(handle, int):
                    self._notify_handle_to_uuid[handle] = notify_uuid
                _LOGGER.debug(
                    "Notify target resolved uuid=%s handle=%s properties=%s",
                    selected_notify.uuid,
                    getattr(selected_notify, "handle", "?"),
                    sorted(getattr(selected_notify, "properties", [])),
                )
            else:
                _LOGGER.warning(
                    "Notify characteristic %s not found; using UUID fallback",
                    notify_uuid,
                )
                resolved_notifies.append(notify_uuid)

        self._notify_targets = resolved_notifies

    async def async_force_rebond(self) -> bool:
        """Try to clear stale bond state before startup, then reconnect."""
        if not self._client:
            return False

        address = self.address or (
            self.ble_device.address if self.ble_device else "unknown"
        )
        _LOGGER.debug("Force rebond requested for %s", address)

        unpaired = await self.async_unpair()
        if not unpaired:
            _LOGGER.warning(
                "Force rebond skipped for %s because unpair is unavailable or failed",
                address,
            )
            if not self.connected:
                with contextlib.suppress(Exception):
                    await self._client.connect()
                    _LOGGER.debug(
                        "Recovered connection after failed force rebond for %s", address
                    )
            return False

        # Backends often drop the ACL immediately after unpair.
        if self.connected:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
        await asyncio.sleep(0.3)
        await self._client.connect()
        _LOGGER.debug("Reconnected after force rebond for %s", address)
        return True

    async def async_unpair(self) -> bool:
        """Attempt to remove the current bond if backend supports it."""
        if not self._client or not hasattr(self._client, "unpair"):
            return False

        try:
            unpaired = await self._client.unpair()  # type: ignore[func-returns-value]
        except (BleakError, OSError, TimeoutError) as exc:  # pragma: no cover
            _LOGGER.debug("Unpair attempt failed: %s", exc)
        else:
            _LOGGER.debug("Unpair result for %s: %s", self.address, unpaired)
            return True
        return False

    async def async_pair(self) -> None:
        """Attempt to pair/bond if the backend supports it."""
        if not self._client or not hasattr(self._client, "pair"):
            return
        try:
            paired = await self._client.pair()  # type: ignore[func-returns-value]
            _LOGGER.debug("Pair result for %s: %s", self.address, paired)
        except (
            BleakError,
            OSError,
            TimeoutError,
        ) as exc:  # pragma: no cover - backend specific
            _LOGGER.debug("Pair attempt failed: %s", exc)

    async def async_request_mc_info(self) -> None:
        """Request MC info (0x41)."""
        # App sends a short 0x41 command (3 bytes total in decompiled code).
        _LOGGER.debug("Requesting MC info")
        await self.async_send(_build_simple_frame(FRAME_MC_INFO))

    async def async_request_model_info(self) -> None:
        """Request model information (0x03)."""
        _LOGGER.debug("Requesting model info frame 0x03")
        await self.async_send(_build_simple_frame(FRAME_MODEL_INFO))

    async def async_request_optional_probe_0a(self) -> None:
        """Request optional startup probe frame 0x0A."""
        _LOGGER.debug("Requesting optional probe frame 0x0A")
        await self.async_send(_build_simple_frame(FRAME_OPTIONAL_PROBE_0A))

    async def async_send_phone_model(self) -> None:
        """Send phone/client model frame (0x0B)."""
        model = (
            self.config.get("phone_model")
            or self.config.get("client_model")
            or platform.node()
            or "HomeAssistant"
        )
        _LOGGER.debug("Sending phone model info: %s", model)
        await self.async_send(_build_phone_model_frame(str(model)))

    async def async_request_general_setting_capability(self) -> None:
        """Request frame 0x1A (general-setting capability)."""
        _LOGGER.debug("Requesting frame 0x1A general-setting capability")
        await self.async_send(_build_simple_frame(FRAME_GENERAL_SETTING_CAPABILITY))

    async def async_request_mc_info_config(self) -> None:
        """Request frame 0x40 (MC info config flags)."""
        _LOGGER.debug("Requesting frame 0x40 MC info config")
        await self.async_send(_build_simple_frame(FRAME_MC_INFO_CONFIG))

    async def async_request_vehicle_setting_config(self) -> None:
        """Request frame 0x47 (vehicle-setting config flags)."""
        _LOGGER.debug("Requesting frame 0x47 vehicle-setting config")
        await self.async_send(_build_simple_frame(FRAME_VEHICLE_SETTING_CONFIG))

    async def async_request_emc_info(self) -> None:
        """Request EMC vehicle info (0x42)."""
        # Decompiled app sends [0x42, 0x00, 0x01].
        _LOGGER.debug("Requesting EMC info")
        await self.async_send(_build_simple_frame(FRAME_EMC_INFO, tail=0x01))

    async def async_request_common_service(self) -> None:
        """Request common service config (0x1D)."""
        _LOGGER.debug("Requesting common service config")
        await self.async_send(_build_simple_frame(FRAME_COMMON_SERVICE))

    async def async_request_service_indicator(self) -> None:
        """Request service indicator config (0x1E)."""
        _LOGGER.debug("Requesting service indicator config")
        await self.async_send(_build_service_indicator_frame())

    async def async_request_frame_0x45(self) -> None:
        """Request frame 0x45 (riding-log extended metrics)."""
        _LOGGER.debug("Requesting frame 0x45")
        await self.async_send(_build_simple_frame(FRAME_RIDING_LOG_EXT))

    async def async_request_vehicle_settings(self) -> None:
        """Request vehicle settings config (0x48)."""
        _LOGGER.debug("Requesting vehicle settings config")
        await self.async_send(_build_vehicle_settings_frame())

    async def async_request_meter_indication_init(self) -> None:
        """Send the app-observed meter indication init frame (0x08)."""
        _LOGGER.debug("Requesting meter indication init")
        await self.async_send(_build_meter_indication_init_frame())

    async def _send_startup_frame(self, frame_id: int) -> None:
        """Send one startup frame by command ID."""
        if frame_id == FRAME_GENERAL_SETTINGS:
            if self.config.get("startup_time_sync"):
                await self.async_send_time_sync()
            else:
                await self.async_request_general_settings()
            return

        if frame_id == FRAME_MC_INFO:
            await self.async_request_mc_info()
        elif frame_id == FRAME_MODEL_INFO:
            await self.async_request_model_info()
        elif frame_id == FRAME_PHONE_MODEL:
            await self.async_send_phone_model()
        elif frame_id == FRAME_GENERAL_SETTING_CAPABILITY:
            await self.async_request_general_setting_capability()
        elif frame_id == FRAME_MC_INFO_CONFIG:
            await self.async_request_mc_info_config()
        elif frame_id == FRAME_VEHICLE_SETTING_CONFIG:
            await self.async_request_vehicle_setting_config()
        elif frame_id == FRAME_EMC_INFO:
            await self.async_request_emc_info()
        elif frame_id == FRAME_COMMON_SERVICE:
            await self.async_request_common_service()
        elif frame_id == FRAME_SERVICE_INDICATOR:
            await self.async_request_service_indicator()
        elif frame_id == FRAME_OPTIONAL_PROBE_0A:
            await self.async_request_optional_probe_0a()
        elif frame_id == FRAME_RIDING_LOG_EXT:
            await self.async_request_frame_0x45()
        elif frame_id == FRAME_VEHICLE_SETTINGS:
            await self.async_request_vehicle_settings()
        elif frame_id == FRAME_METER_INDICATION_INIT:
            await self.async_request_meter_indication_init()
        else:
            await self.async_send(_build_simple_frame(frame_id))

    async def async_startup_sequence(self) -> None:
        """Send the startup frames the app typically emits after connect."""
        startup_delay = float(self.config.get("startup_delay_s", 0))
        if startup_delay > 0:
            _LOGGER.debug("Waiting %ss before startup frames", startup_delay)
            await asyncio.sleep(startup_delay)

        startup_source = "default startup frames"
        if self.startup_frame_profiles:
            profile_index = min(
                self._startup_profile_index, len(self.startup_frame_profiles) - 1
            )
            resolved = list(self.startup_frame_profiles[profile_index])
            startup_source = (
                f"profile {profile_index + 1}/{len(self.startup_frame_profiles)}"
            )
        else:
            frames = self.config.get("startup_frames")
            if frames:
                startup_source = "configured startup_frames"
            else:
                frames = DEFAULT_STARTUP_FRAMES
            resolved = _parse_frame_id_list(frames)
        if not resolved:
            _LOGGER.debug("Startup frame list resolved to empty; skipping sequence")
            return
        _LOGGER.debug(
            "Startup sequence resolved (%s frames) from %s: %s",
            len(resolved),
            startup_source,
            ", ".join(f"0x{frame_id:02X}" for frame_id in resolved),
        )
        _LOGGER.debug(
            (
                "Startup response policy: require_startup_responses=%s "
                "startup_wait_frames=%s startup_no_wait_frames=%s timeout=%.2fs poll=%.2fs"
            ),
            self.require_startup_responses,
            sorted(self.startup_wait_frames),
            sorted(self.startup_no_wait_frames),
            self.startup_wait_timeout_s,
            self.startup_wait_poll_s,
        )

        inter_delay = float(self.config.get("startup_inter_frame_delay_s", 0.2))
        for idx, frame_id in enumerate(resolved):
            should_wait = self._should_wait_for_startup_frame(frame_id)
            max_attempts = 1 + self.startup_retries if should_wait else 1
            for attempt in range(1, max_attempts + 1):
                start_index = len(self._pending_frames)
                _LOGGER.debug(
                    (
                        "Startup step %s/%s sending 0x%02X "
                        "(pending_before=%s should_wait=%s attempt=%s/%s)"
                    ),
                    idx + 1,
                    len(resolved),
                    frame_id,
                    start_index,
                    should_wait,
                    attempt,
                    max_attempts,
                )
                await self._send_startup_frame(frame_id)

                if not should_wait:
                    break
                try:
                    await self._wait_for_startup_response(
                        frame_id, start_index=start_index
                    )
                    break
                except TimeoutError:
                    if attempt >= max_attempts:
                        raise
                    _LOGGER.warning(
                        (
                            "No startup response for 0x%02X on attempt %s/%s; "
                            "retrying after %.2fs"
                        ),
                        frame_id,
                        attempt,
                        max_attempts,
                        self.startup_retry_delay_s,
                    )
                    if self.startup_retry_delay_s > 0:
                        await asyncio.sleep(self.startup_retry_delay_s)

            if idx < len(resolved) - 1 and inter_delay > 0:
                await asyncio.sleep(inter_delay)

    def _should_wait_for_startup_frame(self, frame_id: int) -> bool:
        """Return whether startup should block waiting for this frame response."""
        if frame_id in self.startup_no_wait_frames:
            return False
        if self.startup_wait_frames:
            return frame_id in self.startup_wait_frames
        return self.require_startup_responses

    def advance_startup_profile(self) -> bool:
        """Move to the next configured startup profile if available."""
        if not self.startup_frame_profiles:
            return False
        next_index = self._startup_profile_index + 1
        if next_index >= len(self.startup_frame_profiles):
            return False

        self._startup_profile_index = next_index
        profile = self.startup_frame_profiles[next_index]
        _LOGGER.warning(
            "Switching startup frame profile to %s/%s: %s",
            next_index + 1,
            len(self.startup_frame_profiles),
            ", ".join(f"0x{frame_id:02X}" for frame_id in profile),
        )
        return True

    async def _wait_for_startup_response(
        self, command_id: int, *, start_index: int
    ) -> bytes:
        """Wait for the app-observed response/ack frame for a startup command."""
        predicate, expected = _startup_response_matcher(command_id)
        _LOGGER.debug(
            "Waiting up to %.2fs for startup response to 0x%02X (%s)",
            self.startup_wait_timeout_s,
            command_id,
            expected,
        )
        frame = await self._wait_for_frame(
            predicate,
            timeout=self.startup_wait_timeout_s,
            start_index=start_index,
            description=f"response to 0x{command_id:02X} ({expected})",
        )
        _LOGGER.debug(
            "Matched startup response for 0x%02X: frame=0x%02X raw=%s",
            command_id,
            frame[0],
            frame.hex(),
        )
        return frame

    async def _wait_for_frame(
        self,
        predicate: Callable[[bytes], bool],
        *,
        timeout: float,
        start_index: int,
        description: str,
    ) -> bytes:
        """Wait for a frame matching the predicate from pending notifications."""
        deadline = asyncio.get_running_loop().time() + timeout
        cursor = start_index
        while True:
            pending_len = len(self._pending_frames)
            for idx in range(cursor, pending_len):
                frame = self._pending_frames[idx]
                if predicate(frame):
                    return self._pending_frames.pop(idx)
            cursor = pending_len

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for {description}; "
                    f"pending_frames={len(self._pending_frames)} "
                    f"recent={self._pending_frame_summary()}"
                )

            await asyncio.sleep(min(self.startup_wait_poll_s, remaining))

    def _track_pending_frame(self, payload: bytes) -> None:
        """Keep a bounded FIFO of received frames for startup response matching."""
        self._pending_frames.append(payload)
        overflow = len(self._pending_frames) - self._max_pending_frames
        if overflow > 0:
            del self._pending_frames[:overflow]

    def _pending_frame_summary(self, limit: int = 8) -> str:
        """Return a compact summary of recently seen pending frames."""
        if not self._pending_frames:
            return "[]"
        tail = self._pending_frames[-limit:]
        summary = ", ".join(f"0x{frame[0]:02X}" for frame in tail if frame)
        return f"[{summary}]"

    async def async_send_time_sync(
        self,
        *,
        shift_status: int = 1,
        shift_level: int = 1,
        when: datetime | None = None,
    ) -> None:
        """Send a time sync frame (0x1B)."""
        when = when or datetime.now()
        shift_level = max(0, min(63, shift_level))
        shift_status = max(0, min(3, shift_status))
        _LOGGER.debug(
            "Sending time sync shift_status=%s shift_level=%s when=%s",
            shift_status,
            shift_level,
            when.isoformat(),
        )
        frame = bytes(
            [
                0x1B,
                0x0C,
                0x00,
                0xFF,
                0xFF,
                0x05,
                0x4A,
                0x01,  # request/ack flag used by app
                ((shift_status & 0x03) << 6) | (shift_level & 0x3F),
                when.day & 0x3F,
                when.month & 0x0F,
                (when.year - 2000) & 0xFF,
                when.hour & 0x1F,
                when.minute & 0x3F,
                when.second & 0x3F,
            ]
        )
        await self.async_send(frame)

    async def async_request_general_settings(self) -> None:
        """Request general settings (0x1B)."""
        _LOGGER.debug("Requesting general settings")
        await self.async_send(_build_general_settings_request_frame())

    def _handle_notify(
        self, sender: BleakGATTCharacteristic | int, data: bytearray
    ) -> None:
        """Handle notify frames emitted by the BLE characteristics."""
        if not data:
            return
        payload = bytes(data)
        self._track_pending_frame(payload)
        if isinstance(sender, BleakGATTCharacteristic):
            sender_id = sender.uuid
        elif isinstance(sender, int):
            sender_id = self._notify_handle_to_uuid.get(sender, f"handle:{sender}")
        else:
            sender_id = str(sender)
        if self.log_all_frames or self.debug:
            _LOGGER.debug(
                "Notification from %s frame=0x%02X len=%s raw=%s",
                sender_id,
                data[0],
                len(data),
                payload.hex(),
            )
        frame_id = data[0]
        parsed: dict | None = None

        if frame_id == FRAME_GENERAL_SETTINGS:
            parsed = parse_general_settings(payload, self.last_general_setting_capability)
            self.last_general = parsed
            time_fields_supported: bool | None = None
            shift_lamp_supported: bool | None = None
            if self.last_general_setting_capability:
                day = self.last_general_setting_capability.get("supports_day_setting")
                month = self.last_general_setting_capability.get("supports_month_setting")
                year = self.last_general_setting_capability.get("supports_year_setting")
                hour = self.last_general_setting_capability.get("supports_hour_setting")
                minute = self.last_general_setting_capability.get("supports_minute_setting")
                second = self.last_general_setting_capability.get("supports_second_setting")
                shift_lamp_supported = self.last_general_setting_capability.get(
                    "shift_lamp_level_supported"
                )
                if all(
                    isinstance(flag, bool)
                    for flag in (day, month, year, hour, minute, second)
                ):
                    time_fields_supported = bool(
                        day and month and year and hour and minute and second
                    )
            _LOGGER.info(
                (
                    "Parsed frame 0x1B general settings: "
                    "shift_lamp_supported=%s time_fields_supported=%s "
                    "shift_lamp_status=%s shift_lamp_level=%s shift_lamp_rpm=%s "
                    "date=%s-%s-%s time=%s:%s:%s"
                ),
                shift_lamp_supported,
                time_fields_supported,
                parsed.get("shift_lamp_status"),
                parsed.get("shift_lamp_level"),
                parsed.get("shift_lamp_rpm"),
                parsed.get("year"),
                parsed.get("month"),
                parsed.get("day"),
                parsed.get("hour"),
                parsed.get("minute"),
                parsed.get("second"),
            )
            _LOGGER.debug("Parsed general settings frame: %s", parsed)
            if not (self.log_1b or self.debug):
                parsed = None
        elif frame_id == FRAME_METER_INDICATION_INIT:
            parsed = parse_meter_indication_init(payload)
            _LOGGER.info(
                (
                    "Parsed frame 0x08 meter indication init: "
                    "block_id=0x%02X command=0x%02X enabled=%s "
                    "param_1=%s param_2=%s param_3=%s param_4=%s "
                    "is_default_profile=%s"
                ),
                parsed.get("block_id", 0),
                parsed.get("command_id", 0),
                parsed.get("enabled"),
                parsed.get("param_1"),
                parsed.get("param_2"),
                parsed.get("param_3"),
                parsed.get("param_4"),
                parsed.get("is_default_profile"),
            )
            _LOGGER.debug("Parsed frame 0x08 meter indication init: %s", parsed)
        elif frame_id == FRAME_PHONE_MODEL:
            parsed = parse_phone_model(payload)
            _LOGGER.info(
                "Parsed frame 0x0B phone model: text=%s chunk_ids=%s",
                parsed.get("text"),
                parsed.get("chunk_ids"),
            )
            _LOGGER.debug("Parsed frame 0x0B phone model: %s", parsed)
        elif frame_id == FRAME_EMC_INFO:
            parsed = parse_emc_info(payload)
            if parsed.get("packet_type") == "service_indicator_config_like":
                _LOGGER.info(
                    (
                        "Parsed frame 0x42 EMC info: packet_type=%s valid=%s "
                        "kawasaki_supported=%s rider_supported=%s oil_supported=%s "
                        "supported_count=%s unsupported_count=%s"
                    ),
                    parsed.get("packet_type"),
                    parsed.get("config_valid"),
                    parsed.get("kawasaki_service_supported"),
                    parsed.get("rider_setting_supported"),
                    parsed.get("oil_change_supported"),
                    parsed.get("supported_count"),
                    parsed.get("unsupported_count"),
                )
            else:
                _LOGGER.info(
                    (
                        "Parsed frame 0x42 EMC info: packet_type=%s payload_len=%s "
                        "text=%s block_id=%s block_value=%s"
                    ),
                    parsed.get("packet_type"),
                    parsed.get("payload_len"),
                    parsed.get("text"),
                    parsed.get("block_id"),
                    parsed.get("block_value"),
                )
            _LOGGER.debug("Parsed frame 0x42 EMC info: %s", parsed)
        elif frame_id == FRAME_ACK:
            parsed = parse_ack(payload)
            ack_command = parsed.get("ack_command")
            ack_command_name = parsed.get("ack_command_name")
            result_code = parsed.get("result_code")
            result_text = parsed.get("result_text")
            if isinstance(ack_command, int):
                if ack_command == FRAME_PHONE_MODEL:
                    _LOGGER.info(
                        "Received ACK 0x20: command=0x%02X (%s) text=%s",
                        ack_command,
                        (
                            ack_command_name
                            if isinstance(ack_command_name, str)
                            else _frame_name(ack_command)
                        ),
                        parsed.get("phone_model_text"),
                    )
                else:
                    _LOGGER.info(
                        "Received ACK 0x20: command=0x%02X (%s) result=%s",
                        ack_command,
                        (
                            ack_command_name
                            if isinstance(ack_command_name, str)
                            else _frame_name(ack_command)
                        ),
                        (
                            f"0x{result_code:02X} ({result_text})"
                            if isinstance(result_code, int)
                            else "unknown"
                        ),
                    )
                if ack_command == FRAME_METER_INDICATION_INIT:
                    _LOGGER.info(
                        (
                            "ACK details for frame 0x08: block_id=0x%02X command=0x%02X "
                            "param_1=%s param_2=%s param_3=%s param_4=%s"
                        ),
                        parsed.get("meter_indication_block_id", 0),
                        parsed.get("meter_indication_command_id", 0),
                        parsed.get("meter_indication_param_1"),
                        parsed.get("meter_indication_param_2"),
                        parsed.get("meter_indication_param_3"),
                        parsed.get("meter_indication_param_4"),
                    )
                if ack_command == FRAME_PHONE_MODEL:
                    _LOGGER.info(
                        "ACK details for frame 0x0B: chunk_ids=%s",
                        parsed.get("phone_model_chunk_ids"),
                    )
                if ack_command == FRAME_EMC_INFO:
                    _LOGGER.info(
                        "ACK details for frame 0x42: status=%s",
                        parsed.get("result_text"),
                    )
            else:
                _LOGGER.info("Received ACK 0x20: %s", parsed)
            _LOGGER.debug("Parsed ACK frame: %s", parsed)
        elif frame_id == FRAME_MODEL_INFO:
            parsed = parse_model_info(payload)
            vin = parsed.get("vin")
            if isinstance(vin, str) and vin:
                _LOGGER.info("Received VIN from frame 0x03: %s", vin)
            _LOGGER.debug("Parsed model info frame: %s", parsed)
        elif frame_id == FRAME_GENERAL_SETTING_CAPABILITY:
            parsed = parse_general_setting_capability(payload)
            self.last_general_setting_capability = parsed
            _LOGGER.info(
                (
                    "Parsed frame 0x1A general-setting capability: "
                    "valid=%s shift_lamp_supported=%s shift_lamp_min=%s "
                    "shift_lamp_max=%s"
                ),
                parsed.get("config_valid"),
                parsed.get("shift_lamp_level_supported"),
                parsed.get("shift_lamp_level_min"),
                parsed.get("shift_lamp_level_max"),
            )
            _LOGGER.debug("Parsed frame 0x1A general-setting capability: %s", parsed)
        elif frame_id == FRAME_MC_INFO_CONFIG:
            parsed = parse_info_config_flags(payload)
            self.last_info_config_flags = {
                name: value
                for name, _, _, _ in _INFO_CONFIG_FIELD_LAYOUT
                if isinstance((value := parsed.get(name)), int)
            }
            _LOGGER.info(
                (
                    "Parsed frame 0x40 MC info config: valid=%s supported_count=%s "
                    "unsupported_count=%s supported=[%s] unsupported=[%s]"
                ),
                parsed.get("config_valid"),
                parsed.get("supported_count"),
                parsed.get("unsupported_count"),
                parsed.get("supported_fields"),
                parsed.get("unsupported_fields"),
            )
            _LOGGER.debug("Parsed frame 0x40 MC info config: %s", parsed)
        elif frame_id == FRAME_VEHICLE_SETTING_CONFIG:
            parsed = parse_tuning_config_flags(payload)
            self.last_tuning_config_flags = {
                name: value
                for name, _, _, _ in _TUNING_CONFIG_FIELD_LAYOUT
                if isinstance((value := parsed.get(name)), int)
            }
            _LOGGER.info(
                (
                    "Parsed frame 0x47 vehicle-setting config: supported_count=%s "
                    "unsupported_count=%s supported=[%s] unsupported=[%s]"
                ),
                parsed.get("supported_count"),
                parsed.get("unsupported_count"),
                parsed.get("supported_fields"),
                parsed.get("unsupported_fields"),
            )
            _LOGGER.debug("Parsed frame 0x47 vehicle-setting config: %s", parsed)
        elif frame_id == FRAME_COMMON_SERVICE:
            parsed = parse_common_service_config_flags(payload)
            if parsed.get("config_valid") is True:
                self.last_common_service_config_flags = {
                    name: value
                    for name, _, _, _ in _COMMON_SERVICE_CONFIG_FIELD_LAYOUT
                    if isinstance((value := parsed.get(name)), int)
                }
            _LOGGER.info(
                (
                    "Parsed frame 0x1D common-service config: valid=%s "
                    "kawasaki_supported=%s rider_supported=%s oil_supported=%s "
                    "supported_count=%s unsupported_count=%s "
                    "supported=[%s] unsupported=[%s]"
                ),
                parsed.get("config_valid"),
                parsed.get("kawasaki_service_supported"),
                parsed.get("rider_setting_supported"),
                parsed.get("oil_change_supported"),
                parsed.get("supported_count"),
                parsed.get("unsupported_count"),
                parsed.get("supported_fields"),
                parsed.get("unsupported_fields"),
            )
            _LOGGER.debug("Parsed frame 0x1D common-service config: %s", parsed)
        elif frame_id == FRAME_SERVICE_INDICATOR:
            parsed = parse_service_indicator(
                payload, self.config, self.last_common_service_config_flags
            )
            self.last_service_indicator = parsed
            _LOGGER.info(
                (
                    "Parsed frame 0x1E service indicator: "
                    "kawasaki_supported=%s rider_supported=%s oil_supported=%s "
                    "kawasaki_notify=%s kawasaki_due=%s-%s-%s dist=%s "
                    "rider_notify=%s rider_due=%s-%s-%s dist=%s "
                    "oil_notify=%s oil_due=%s-%s-%s dist=%s"
                ),
                parsed.get("kawasaki_service_supported"),
                parsed.get("rider_setting_supported"),
                parsed.get("oil_change_supported"),
                parsed.get("kawasaki_service_notify"),
                parsed.get("kawasaki_service_year"),
                parsed.get("kawasaki_service_month"),
                parsed.get("kawasaki_service_day"),
                parsed.get("kawasaki_service_distance"),
                parsed.get("rider_setting_notify"),
                parsed.get("rider_setting_year"),
                parsed.get("rider_setting_month"),
                parsed.get("rider_setting_day"),
                parsed.get("rider_setting_distance"),
                parsed.get("oil_change_notify"),
                parsed.get("oil_change_year"),
                parsed.get("oil_change_month"),
                parsed.get("oil_change_day"),
                parsed.get("oil_change_distance"),
            )
            _LOGGER.debug("Parsed frame 0x1E service indicator: %s", parsed)
        elif frame_id == FRAME_VEHICLE_SETTINGS:
            parsed = parse_vehicle_settings(
                payload, self.config, self.last_tuning_config_flags
            )
            self.last_vehicle_settings = parsed
            _LOGGER.info(
                (
                    "Parsed frame 0x48 vehicle settings: decoded_count=%s "
                    "decoded=[%s] meter_cap=%s ecu_cap=%s "
                    "ktrc=%s riding_mode=%s kqs=%s kebc=%s power=%s"
                ),
                parsed.get("decoded_count"),
                parsed.get("decoded_fields"),
                parsed.get("meter_tuning_capability"),
                parsed.get("ecu_tuning_capability"),
                parsed.get("ktrc"),
                parsed.get("riding_mode"),
                parsed.get("kqs"),
                parsed.get("kebc"),
                parsed.get("power"),
            )
            _LOGGER.debug("Parsed frame 0x48 vehicle settings: %s", parsed)
        elif frame_id == FRAME_RIDING_LOG_MID:
            parsed = parse_riding_log_mid(
                payload, self.rpm_mode, self.wheel_mode, self.config
            )
            self.last_riding_log = parsed
            _LOGGER.debug(
                "Parsed riding frame rpm=%s speed=%s gear=%s throttle=%s",
                parsed.get("rpm"),
                parsed.get("wheel_kph"),
                parsed.get("gear"),
                parsed.get("throttle"),
            )
        elif frame_id == FRAME_MC_INFO:
            parsed = parse_mc_info(payload, self.config, self.last_info_config_flags)
            self.last_mc_info = parsed
            _LOGGER.info(
                (
                    "Parsed frame 0x41 MC info: ecu_battery12V=%s meter_battery12V=%s "
                    "odometer=%s fuel_gauge=%s"
                ),
                parsed.get("ecu_battery12V"),
                parsed.get("meter_battery12V"),
                parsed.get("odometer"),
                parsed.get("fuel_gauge"),
            )
            _LOGGER.debug("Parsed MC info frame: %s", parsed)
        elif frame_id == FRAME_RIDING_LOG_EXT:
            parsed = parse_riding_log_ext(
                payload, self.config, self.last_info_config_flags
            )
            self.last_riding_log_ext = parsed
            _LOGGER.debug(
                (
                    "Parsed frame 0x45 water=%s oil=%s inlet=%s "
                    "tire_fr=%s tire_rr=%s odometer=%s"
                ),
                parsed.get("water_temperature"),
                parsed.get("oil_temperature"),
                parsed.get("inlet_air_temperature"),
                parsed.get("tire_pressure_fr"),
                parsed.get("tire_pressure_rr"),
                parsed.get("odometer"),
            )
        elif frame_id == FRAME_RIDING_LOG_HIGH:
            parsed = parse_riding_log_high(payload, self.config)
            self.last_riding_log_high = parsed
            _LOGGER.debug(
                (
                    "Parsed frame 0x4B rr_stroke=%s fr_stroke=%s "
                    "ay=%s ax=%s az=%s"
                ),
                parsed.get("rr_suspension_stroke"),
                parsed.get("fr_suspension_stroke"),
                parsed.get("ay"),
                parsed.get("ax"),
                parsed.get("az"),
            )
        elif frame_id == FRAME_STATUS_REPORT:
            parsed = parse_status_report(payload)
            status_type = parsed.get("status_type")
            if status_type == "block_result":
                block_id = parsed.get("block_id")
                block_name = parsed.get("block_name")
                result_code = parsed.get("result_code")
                result_text = parsed.get("result_text")
                if isinstance(block_id, int) and isinstance(result_code, int):
                    _LOGGER.info(
                        (
                            "Parsed frame 0x30 status result: "
                            "block_id=0x%02X (%s) result=0x%02X (%s)"
                        ),
                        block_id,
                        block_name if isinstance(block_name, str) else _frame_name(block_id),
                        result_code,
                        result_text,
                    )
                else:
                    _LOGGER.info("Parsed frame 0x30 status result: %s", parsed)
            elif status_type == "text_chunks":
                text = parsed.get("text")
                _LOGGER.info(
                    "Parsed frame 0x30 text chunks: %s",
                    text if isinstance(text, str) and text else parsed,
                )
            _LOGGER.debug("Parsed frame 0x30 status report: %s", parsed)
        elif self.debug:
            _LOGGER.debug("Unhandled frame 0x%02X bytes=%s", frame_id, payload.hex())

        if self.on_frame:
            _LOGGER.debug("Dispatching frame 0x%02X to callback", frame_id)
            self.on_frame(frame_id, parsed, payload)


def _startup_response_matcher(command_id: int) -> tuple[Callable[[bytes], bool], str]:
    """Return a predicate and description for startup response matching."""
    response_by_same_frame = {
        FRAME_MODEL_INFO,
        FRAME_MC_INFO_CONFIG,
        FRAME_GENERAL_SETTING_CAPABILITY,
        FRAME_COMMON_SERVICE,
        FRAME_VEHICLE_SETTING_CONFIG,
        FRAME_MC_INFO,
        FRAME_GENERAL_SETTINGS,
        FRAME_VEHICLE_SETTINGS,
        FRAME_SERVICE_INDICATOR,
    }

    if command_id in response_by_same_frame:
        return (
            lambda payload, expected=command_id: (payload and payload[0] == expected)
            or (
                len(payload) > 3 and payload[0] == FRAME_ACK and payload[3] == expected
            ),
            f"frame 0x{command_id:02X} or ACK cmd=0x{command_id:02X}",
        )

    if command_id == FRAME_METER_INDICATION_INIT:
        # Different app versions have used ACK cmd 0x08 and 0x13 for frame 0x08.
        return (
            lambda payload: len(payload) > 3
            and payload[0] == FRAME_ACK
            and payload[3] in (0x08, 0x13),
            "ACK 0x20 cmd in {0x08,0x13} (meter indication)",
        )

    if command_id in {FRAME_RIDING_LOG_EXT, FRAME_EMC_INFO}:
        return (
            lambda payload, expected=command_id: len(payload) > 3
            and payload[0] == FRAME_ACK
            and payload[3] == expected,
            f"ACK 0x20 cmd=0x{command_id:02X}",
        )

    if command_id == FRAME_PHONE_MODEL:
        return (
            lambda payload: bool(payload) and payload[0] == FRAME_ACK,
            "ACK 0x20",
        )

    # Fallback: accept either same frame ID or a generic ACK with matching command.
    return (
        lambda payload, expected=command_id: (payload and payload[0] == expected)
        or (len(payload) > 3 and payload[0] == FRAME_ACK and payload[3] == expected),
        f"frame 0x{command_id:02X} or ACK 0x20 cmd=0x{command_id:02X}",
    )


def _auto_choose(raw: int, scaled: int, high: int = 20000, max_ok: int = 15000) -> int:
    """Pick a plausible value between two interpretations."""
    if raw > high and scaled <= max_ok:
        return scaled
    if raw == 0 and scaled > 0:
        return scaled
    return raw


def _build_simple_frame(frame_id: int, *, tail: int = 0x00) -> bytes:
    """Build a simple 3-byte frame used by multiple requests."""
    return bytes([frame_id & 0xFF, 0x00, tail & 0xFF])


def _build_service_indicator_frame() -> bytes:
    """Build the 0x1E service indicator request frame."""
    frame = bytearray([0xFF] * 45)
    frame[0] = FRAME_SERVICE_INDICATOR
    frame[1] = 0x2A
    frame[2] = 0x01
    frame[5] = 0x05
    frame[6] = 0x0C
    frame[7] = 0x00
    frame[15] = 0x05
    frame[16] = 0x0D
    frame[17] = 0x00
    frame[25] = 0x05
    frame[26] = 0x0E
    frame[27] = 0x00
    return bytes(frame)


def _build_vehicle_settings_frame() -> bytes:
    """Build the 0x48 vehicle settings request frame."""
    frame = bytearray([0xFF] * 45)
    frame[0] = FRAME_VEHICLE_SETTINGS
    frame[1] = 0x2A
    frame[2] = 0x00
    frame[5] = 0x05
    frame[6] = 0x09
    frame[7] = 0x00
    return bytes(frame)


def _build_general_settings_request_frame() -> bytes:
    """Build the 0x1B general settings request frame."""
    frame = bytearray([0xFF] * 15)
    frame[0] = FRAME_GENERAL_SETTINGS
    frame[1] = 0x0C
    frame[2] = 0x00
    frame[3] = 0xFF
    frame[4] = 0xFF
    frame[5] = 0x05
    frame[6] = 0x0A
    frame[7] = 0x00
    return bytes(frame)


def _build_meter_indication_init_frame() -> bytes:
    """Build the app-observed 0x08 meter indication init frame."""
    return bytes(
        [
            FRAME_METER_INDICATION_INIT,
            0x0C,
            0x00,
            0xFF,
            0xFF,
            0x0A,
            0x08,
            0x01,
            0x78,
            0x03,
            0xE8,
            0x00,
            0xC8,
            0x00,
            0x64,
        ]
    )


def _build_phone_model_frame(model: str) -> bytes:
    """Build the 0x0B phone/client model frame."""
    # App capture uses 0x00 padding for unused model bytes with 0xFF 0xFF header.
    data = bytearray([0x00] * 35)
    data[0] = FRAME_PHONE_MODEL
    data[1] = 0x20
    data[2] = 0x00
    data[3] = 0xFF
    data[4] = 0xFF

    raw = model.encode("utf-8", errors="ignore")
    max_chunks = 3
    chunk_size = 8
    for chunk_index in range(max_chunks):
        start = chunk_index * chunk_size
        if start >= len(raw):
            break
        chunk = raw[start : start + chunk_size]
        base = 5 + chunk_index * 10
        data[base] = 0x05
        data[base + 1] = chunk_index + 1
        data[base + 2 : base + 2 + len(chunk)] = chunk
    return bytes(data)


def _choose_in_range(
    a: float | None, b: float | None, low: float, high: float
) -> float | None:
    if a is not None and low <= a <= high:
        return a
    if b is not None and low <= b <= high:
        return b
    return a if a is not None else b


def parse_rpm(data: bytes, mode: str) -> int | None:
    """Parse engine RPM from frame data."""
    if len(data) < 13:
        return None
    raw0 = ((data[11] & 0x7F) << 8) | (data[12] & 0xFF)
    scaled_quarter = int((((data[11] & 0xFF) << 8) | (data[12] & 0xFF)) * 0.25)

    if mode == "raw":
        return raw0
    if mode == "quarter":
        return scaled_quarter
    return _auto_choose(raw0, scaled_quarter)


def parse_wheel_speed_kph(data: bytes, mode: str) -> int | None:
    """Parse wheel speed in kph from frame data."""
    if len(data) < 11:
        return None
    raw = ((data[9] & 0xFF) << 8) | (data[10] & 0xFF)
    scaled = int(raw * 0.01220703125)
    raw1 = ((data[9] & 0x01) << 8) | (data[10] & 0xFF)

    if mode == "raw":
        return raw
    if mode == "scaled":
        return scaled
    if mode == "raw1":
        return raw1
    if 0 <= scaled <= 300:
        return scaled
    if 0 <= raw1 <= 300:
        return raw1
    return scaled


def _u8(data: bytes, idx: int) -> int | None:
    """Return an unsigned byte or None if out of range."""
    if idx >= len(data):
        return None
    return data[idx] & 0xFF


def _parse_status_fuel_injection(
    data: bytes, mode: str
) -> tuple[float | None, float | None, float | None]:
    """Parse fuel injection status and return (value, raw, scaled)."""
    if len(data) <= 8:
        return None, None, None
    raw = ((data[7] & 0xFF) << 8) | (data[8] & 0xFF)
    raw_val = raw * 1e-4
    scaled_val = raw_val * 100.0 / 140.0
    if mode == "scale_a":
        return raw_val, raw_val, scaled_val
    if mode == "scale_b":
        return scaled_val, raw_val, scaled_val
    return _choose_in_range(raw_val, scaled_val, 0.0, 1.0), raw_val, scaled_val


def _parse_throttle(
    data: bytes, mode: str
) -> tuple[float | None, float | None, float | None]:
    """Parse throttle and return (value, rider, mechanical)."""
    if len(data) <= 14:
        return None, None, None
    rider = (data[14] & 0xFF) * 0.78125
    mecha = (data[14] & 0xFF) * 0.3921568627
    if mode == "rider":
        return rider, rider, mecha
    if mode == "mecha":
        return mecha, rider, mecha
    return _choose_in_range(mecha, rider, 0.0, 100.0), rider, mecha


def _parse_accel(data: bytes, mode: str) -> float | None:
    """Parse acceleration in g."""
    if len(data) <= 18:
        return None
    raw = ((data[17] & 0x01) << 8) | (data[18] & 0xFF)
    accel_a = raw * 0.01 - 2.0
    accel_b = raw * 0.01
    if mode == "minus2":
        return accel_a
    if mode == "raw":
        return accel_b
    return _choose_in_range(accel_a, accel_b, -5.0, 5.0)


def _parse_lean(data: bytes, mode: str) -> float | None:
    """Parse lean angle in degrees."""
    if len(data) <= 20:
        return None
    raw0 = ((data[19] & 0x07) << 8) | (data[20] & 0xFF)
    raw1 = ((data[19] & 0x0F) << 8) | (data[20] & 0xFF)
    lean_a = raw0 * 0.1953125 - 100.0
    lean_b = raw1 * 0.1
    if mode == "minus100":
        return lean_a
    if mode == "raw":
        return lean_b
    return _choose_in_range(lean_a, lean_b, -90.0, 90.0)


def _parse_wheelie(data: bytes, mode: str) -> tuple[int | None, float | None]:
    """Parse wheelie flag and wheelie angle."""
    wheelie_flag = (data[21] & 0x03) if len(data) > 21 else None
    if len(data) <= 23:
        return wheelie_flag, None
    raw0 = ((data[22] & 0x07) << 8) | (data[23] & 0xFF)
    raw1 = ((data[22] & 0x0F) << 8) | (data[23] & 0xFF)
    ang_a = raw0 * 0.09765625
    ang_b = raw1 * 0.1
    if mode == "scale09765625":
        return wheelie_flag, ang_a
    if mode == "scale0.1":
        return wheelie_flag, ang_b
    return wheelie_flag, _choose_in_range(ang_a, ang_b, 0.0, 60.0)


def _parse_tcs_levels(data: bytes) -> tuple[int | None, int | None]:
    """Parse TCS high/low nibble levels."""
    if len(data) <= 24:
        return None, None
    return (data[24] & 0xF0) >> 4, data[24] & 0x0F


def _parse_torque_pair(
    data: bytes, idx_hi: int, idx_lo: int, mode: str
) -> tuple[int | None, int | None, int | None]:
    """Parse torque pair values."""
    if len(data) <= idx_lo:
        return None, None, None
    raw0 = ((data[idx_hi] & 0x3F) << 8) | (data[idx_lo] & 0xFF)
    raw1 = ((data[idx_hi] & 0x0F) << 8) | (data[idx_lo] & 0xFF)
    val0 = int(raw0 * 0.2)
    val1 = raw1
    if mode == "scaled":
        return val0, val0, val1
    if mode == "raw":
        return val1, val0, val1
    return _auto_choose(val1, val0, high=5000, max_ok=2000), val0, val1


def _parse_abs_statuses(
    data: bytes,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Parse ABS status flags."""
    if len(data) <= 37:
        return None, None, None, None
    b35 = _u8(data, 35)
    b36 = _u8(data, 36)
    b37 = _u8(data, 37)
    if b35 is None or b36 is None or b37 is None or b35 == 0xFF or b36 == 0xFF:
        return None, None, None, None
    abs_cpl_insp_mode = (b37 & 0x10) >> 4
    abs_system_error = (b37 & 0x0C) >> 2
    abs_front_status = b37 & 0x01
    abs_rear_status = (b37 & 0x02) >> 1
    return abs_cpl_insp_mode, abs_system_error, abs_front_status, abs_rear_status


def _parse_front_brake_pressure(data: bytes) -> float | None:
    """Parse front brake pressure."""
    if len(data) <= 39:
        return None
    b35 = _u8(data, 35)
    b36 = _u8(data, 36)
    b39 = _u8(data, 39)
    if (
        b35 is None
        or b36 is None
        or b39 is None
        or b35 == 0xFF
        or b36 == 0xFF
        or b39 == 0xFF
    ):
        return None
    return b39 * 0.1953125


def _parse_abs_target_indicator(
    data: bytes,
) -> tuple[int | None, int | None, int | None]:
    """Parse ABS target/indicator and switching info."""
    if len(data) <= 48:
        return None, None, None
    b45 = _u8(data, 45)
    b46 = _u8(data, 46)
    b47 = _u8(data, 47)
    b48 = _u8(data, 48)
    if b45 is None or b46 is None or b47 is None:
        return None, None, None
    abs_target = None
    abs_indicator = None
    switching_info = None
    if b45 != 0xFF and b46 != 0xFF and (b47 & 0x07) != 0:
        abs_target = (b47 & 0xE0) >> 5
    if b45 != 0xFF and b46 != 0xFF:
        abs_indicator = b47 & 0x07
        if b48 is not None:
            switching_info = b48 & 0x01
    return abs_target, abs_indicator, switching_info


def parse_riding_log_mid(
    data: bytes, rpm_mode: str, wheel_mode: str, cfg: dict
) -> dict:
    """Parse frame 0x4A (Riding Log Mid)."""
    rpm = parse_rpm(data, rpm_mode)
    wheel_kph = parse_wheel_speed_kph(data, wheel_mode)
    supported = cfg.get("supported_fields", {})
    throttle_mode = cfg.get("throttle_mode", "auto")
    status_mode = cfg.get("status_fuel_injection_mode", "auto")
    accel_mode = cfg.get("accel_mode", "auto")
    lean_mode = cfg.get("lean_mode", "auto")
    wheelie_angle_mode = cfg.get("wheelie_angle_mode", "auto")
    rider_torque_mode = cfg.get("rider_torque_mode", "auto")
    engine_torque_request_mode = cfg.get("engine_torque_request_mode", "auto")
    engine_torque_actual_mode = cfg.get("engine_torque_actual_mode", "auto")

    gear = data[13] & 0x0F if len(data) > 13 else None

    (
        status_fuel_injection,
        status_fuel_injection_raw,
        status_fuel_injection_scaled,
    ) = _parse_status_fuel_injection(data, status_mode)

    throttle, throttle_rider, throttle_mecha = _parse_throttle(data, throttle_mode)
    accel = _parse_accel(data, accel_mode)
    lean = _parse_lean(data, lean_mode)
    wheelie_flag, wheelie_angle = _parse_wheelie(data, wheelie_angle_mode)
    tcs_level_hb, tcs_level_lb = _parse_tcs_levels(data)

    (
        rider_torque_request,
        rider_torque_request_scaled,
        rider_torque_request_raw,
    ) = _parse_torque_pair(data, 27, 28, rider_torque_mode)
    (
        engine_torque_request,
        engine_torque_request_scaled,
        engine_torque_request_raw,
    ) = _parse_torque_pair(data, 29, 30, engine_torque_request_mode)
    (
        engine_torque_actual,
        engine_torque_actual_scaled,
        engine_torque_actual_raw,
    ) = _parse_torque_pair(data, 31, 32, engine_torque_actual_mode)

    (
        abs_cpl_insp_mode,
        abs_system_error,
        abs_front_status,
        abs_rear_status,
    ) = _parse_abs_statuses(data)

    front_brake_pressure = _parse_front_brake_pressure(data)
    abs_target, abs_indicator, switching_info = _parse_abs_target_indicator(data)

    payload = {
        "frame": "0x4A",
        "status_fuel_injection": status_fuel_injection,
        "status_fuel_injection_raw": status_fuel_injection_raw,
        "status_fuel_injection_scaled": status_fuel_injection_scaled,
        "rpm": rpm,
        "wheel_kph": wheel_kph,
        "gear": gear,
        "throttle": throttle,
        "throttle_rider": throttle_rider,
        "throttle_mecha": throttle_mecha,
        "lean_deg": lean,
        "accel_g": accel,
        "wheelie_flag": wheelie_flag,
        "wheelie_angle": wheelie_angle,
        "tcs_level_hb": tcs_level_hb,
        "tcs_level_lb": tcs_level_lb,
        "rider_torque_request": rider_torque_request,
        "rider_torque_request_scaled": rider_torque_request_scaled,
        "rider_torque_request_raw": rider_torque_request_raw,
        "engine_torque_request": engine_torque_request,
        "engine_torque_request_scaled": engine_torque_request_scaled,
        "engine_torque_request_raw": engine_torque_request_raw,
        "engine_torque_actual": engine_torque_actual,
        "engine_torque_actual_scaled": engine_torque_actual_scaled,
        "engine_torque_actual_raw": engine_torque_actual_raw,
        "abs_cpl_insp_mode": abs_cpl_insp_mode,
        "abs_system_error": abs_system_error,
        "abs_front_status": abs_front_status,
        "abs_rear_status": abs_rear_status,
        "front_brake_pressure": front_brake_pressure,
        "abs_target": abs_target,
        "abs_indicator": abs_indicator,
        "switching_info": switching_info,
    }

    for key, is_supported in supported.items():
        if not is_supported and key in payload:
            payload[key] = None

    return payload


def parse_info_config_flags(data: bytes) -> dict[str, int | str | bool | None]:
    """Parse frame 0x40 info_config support/scaling flags (Ble5Value.i)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x40"}
    if len(data) < 35:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["related_command"] = data[3] & 0xFF

    for name, index, mask, shift in _INFO_CONFIG_FIELD_LAYOUT:
        mode = (data[index] & mask) >> shift
        out[name] = mode
        out[f"{name}_supported"] = mode in (0, 1)

    # Mirrors Ble5Value.i.a(...) grouping logic used by the app.
    def _group_ready(a_idx: int, b_idx: int, flag_idx: int) -> bool:
        a_raw = data[a_idx] & 0xFF
        b_raw = data[b_idx] & 0xFF
        flag = data[flag_idx] & 0xFF
        return ((a_raw != 0xFF or b_raw != 0xFF) and ((flag & 0x01) == 0))

    config_retry_required = (
        _group_ready(5, 6, 14) or _group_ready(15, 16, 24) or _group_ready(25, 26, 34)
    )
    out["config_retry_required"] = config_retry_required
    out["config_valid"] = not config_retry_required

    supported_names = [
        name
        for name, _, _, _ in _INFO_CONFIG_FIELD_LAYOUT
        if isinstance(out.get(name), int) and out[name] in (0, 1)
    ]
    unsupported_names = [
        name
        for name, _, _, _ in _INFO_CONFIG_FIELD_LAYOUT
        if isinstance(out.get(name), int) and out[name] == 3
    ]
    out["supported_count"] = len(supported_names)
    out["unsupported_count"] = len(unsupported_names)
    out["supported_fields"] = ",".join(supported_names) if supported_names else None
    out["unsupported_fields"] = ",".join(unsupported_names) if unsupported_names else None
    return out


def parse_tuning_config_flags(data: bytes) -> dict[str, int | str | bool | None]:
    """Parse frame 0x47 tuning-config support flags (Ble5Value.y)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x47"}
    if len(data) < 21:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["related_command"] = data[3] & 0xFF

    requires_zero = {
        "kqs",
        "kebc",
        "kecs_preload_mode",
        "kecs_mode",
        "kecs_load_adjustment",
        "kecs_damping_frCom",
        "kecs_damping_frTen",
        "kecs_damping_rrCom",
        "kecs_damping_rrTen",
    }
    supports_012 = {"ktrc"}
    supports_01 = {
        "tuning_capability_fiEcu",
        "riding_mode",
        "power",
        "tuning_capability_meter",
    }

    supported_names: list[str] = []
    unsupported_names: list[str] = []
    for name, index, mask, shift in _TUNING_CONFIG_FIELD_LAYOUT:
        mode = (data[index] & mask) >> shift
        out[name] = mode

        if name in requires_zero:
            is_supported = mode == 0
        elif name in supports_012:
            is_supported = mode in (0, 1, 2)
        elif name in supports_01:
            is_supported = mode in (0, 1)
        else:
            is_supported = mode in (0, 1)
        out[f"{name}_supported"] = is_supported

        if is_supported:
            supported_names.append(name)
        else:
            unsupported_names.append(name)

    out["supported_count"] = len(supported_names)
    out["unsupported_count"] = len(unsupported_names)
    out["supported_fields"] = ",".join(supported_names) if supported_names else None
    out["unsupported_fields"] = ",".join(unsupported_names) if unsupported_names else None
    return out


def parse_common_service_config_flags(
    data: bytes,
) -> dict[str, int | str | bool | None]:
    """Parse frame 0x1D common-service config support flags (Ble5Value.u)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x1D"}
    if len(data) < 15:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["related_command"] = data[3] & 0xFF

    capability_fields = {
        "kawasaki_service_setting_capability",
        "user_setting_capability",
        "oil_change_setting_capability",
    }

    supported_names: list[str] = []
    unsupported_names: list[str] = []
    for name, index, mask, shift in _COMMON_SERVICE_CONFIG_FIELD_LAYOUT:
        mode = (data[index] & mask) >> shift
        out[name] = mode
        if name in capability_fields:
            is_supported = mode in (0, 1)
        else:
            is_supported = mode == 0
        out[f"{name}_supported"] = is_supported
        if is_supported:
            supported_names.append(name)
        else:
            unsupported_names.append(name)

    # Mirrors Ble5Value.u.f11110s semantics in app:
    # retry_required = ((b5 != 0xFF or b6 != 0xFF) and ((b14 & 0x01) == 0))
    # app considers valid/usable when retry_required is False.
    config_retry_required = (
        (((data[5] & 0xFF) != 0xFF) or ((data[6] & 0xFF) != 0xFF))
        and ((data[14] & 0x01) == 0)
    )
    out["config_retry_required"] = config_retry_required
    out["config_valid"] = not config_retry_required
    out["kawasaki_service_supported"] = (
        (out.get("kawasaki_service_setting_capability") in (0, 1))
        and (out.get("kawasaki_service_notify") == 0)
        and (out.get("kawasaki_service_month") == 0)
        and (out.get("kawasaki_service_day") == 0)
        and (out.get("kawasaki_service_year") == 0)
        and (out.get("kawasaki_service_distance") == 0)
    )
    out["rider_setting_supported"] = (
        (out.get("user_setting_capability") in (0, 1))
        and (out.get("user_setting_notify") == 0)
        and (out.get("user_setting_month") == 0)
        and (out.get("user_setting_day") == 0)
        and (out.get("user_setting_year") == 0)
        and (out.get("user_setting_distance") == 0)
    )
    out["oil_change_supported"] = (
        (out.get("oil_change_setting_capability") in (0, 1))
        and (out.get("oil_change_notify") == 0)
        and (out.get("oil_change_month") == 0)
        and (out.get("oil_change_day") == 0)
        and (out.get("oil_change_year") == 0)
        and (out.get("oil_change_distance") == 0)
    )
    out["supported_count"] = len(supported_names)
    out["unsupported_count"] = len(unsupported_names)
    out["supported_fields"] = ",".join(supported_names) if supported_names else None
    out["unsupported_fields"] = (
        ",".join(unsupported_names) if unsupported_names else None
    )
    return out


def parse_mc_info_flags(data: bytes) -> dict[str, int | str]:
    """Parse frame 0x41 feature flags used to gate optional telemetry fields."""
    out: dict[str, int | str] = {"frame": "0x41"}
    if len(data) <= 31:
        out["error"] = "short"
        return out

    # Mirrors BLE5.Ble5Value.i.b(...) for fields used by frame 0x45 parsing.
    total_distance_flag = (data[7] & 0xC0) >> 6
    instant_fuel_flag = (data[31] & 0x0C) >> 2

    out["total_distance_traveled"] = total_distance_flag
    out["engine_fuel_rate"] = (data[7] & 0x0C) >> 2
    out["engine_water_temperature"] = (data[8] & 0xC0) >> 6
    out["engine_oil_temperature"] = (data[8] & 0x30) >> 4
    out["inlet_air_temperature"] = (data[8] & 0x0C) >> 2
    out["odometer"] = (data[27] & 0xC0) >> 6
    out["instant_fuel_consumption"] = instant_fuel_flag
    return out


def parse_mc_info(
    data: bytes,
    cfg: dict,
    info_flags: dict[str, int] | None = None,
) -> dict[str, float | int | str | None]:
    """Parse frame 0x41 (MC info / vehicle snapshot)."""
    out: dict[str, float | int | str | None] = {"frame": "0x41"}
    supported = cfg.get("supported_fields", {})
    config_flags = cfg.get("info_config_flags", {})

    def gate(flag: str, expected: int = 0) -> bool:
        value: int | None = None
        if info_flags and flag in info_flags and isinstance(info_flags[flag], int):
            value = info_flags[flag]
        elif flag in config_flags and isinstance(config_flags[flag], int):
            value = config_flags[flag]
        # If the config gate is unknown, parse opportunistically.
        return value is None or value == expected

    total_fuel_consumed: float | None = None
    if len(data) > 10 and gate("total_fuel_consumed", 0):
        raw = (
            ((data[7] & 0xFF) << 24)
            | ((data[8] & 0xFF) << 16)
            | ((data[9] & 0xFF) << 8)
            | (data[10] & 0xFF)
        )
        total_fuel_consumed = raw * 0.01

    ecu_battery12v: float | None = None
    if len(data) > 14 and gate("ecu_battery12V", 0):
        ecu_battery12v = ((data[14] & 0xFF) * 20.0) / 256.0

    odometer: int | None = None
    if len(data) > 29 and gate("odometer", 0):
        odometer = (
            ((data[27] & 0x0F) << 16)
            | ((data[28] & 0xFF) << 8)
            | (data[29] & 0xFF)
        )

    fuel_gauge: int | None = None
    if len(data) > 30 and gate("fuel_gauge", 0):
        fuel_gauge = data[30] & 0x0F

    average_fuel_mileage: float | None = None
    if len(data) > 33 and gate("average_fuel_mileage", 0):
        raw = ((data[32] & 0x03) << 8) | (data[33] & 0xFF)
        average_fuel_mileage = raw * 0.1

    meter_battery12v: float | None = None
    if len(data) > 34 and gate("meter_battery12V", 0):
        meter_battery12v = (data[34] & 0xFF) * 0.1

    trip_a: float | None = None
    if len(data) > 39 and gate("tripA", 0):
        raw = ((data[37] & 0x01) << 16) | ((data[38] & 0xFF) << 8) | (data[39] & 0xFF)
        trip_a = raw * 0.1

    trip_b: float | None = None
    if len(data) > 42 and gate("tripB", 0):
        raw = ((data[40] & 0x01) << 16) | ((data[41] & 0xFF) << 8) | (data[42] & 0xFF)
        trip_b = raw * 0.1

    average_speed: int | None = None
    if len(data) > 43 and gate("average_speed", 0):
        average_speed = data[43] & 0xFF

    outer_air_temperature: int | None = None
    if len(data) > 44 and gate("outer_air_temperature", 0):
        outer_air_temperature = (data[44] & 0xFF) - 60

    range_symbol: int | None = None
    if len(data) > 47 and gate("range_symbol", 0):
        range_symbol = (data[47] & 0x30) >> 4

    range_value: int | None = None
    if len(data) > 48 and gate("range", 0):
        range_value = ((data[47] & 0x03) << 8) | (data[48] & 0xFF)

    fuel_consumption: float | None = None
    if len(data) > 50 and gate("fuel_consumption", 0):
        raw = ((data[49] & 0x03) << 8) | (data[50] & 0xFF)
        fuel_consumption = raw * 0.1

    total_time: int | None = None
    if len(data) > 52 and gate("total_time", 0):
        total_time = ((data[51] & 0x1F) << 8) | (data[52] & 0xFF)

    out.update(
        {
            "total_fuel_consumed": total_fuel_consumed,
            "ecu_battery12V": ecu_battery12v,
            "odometer": odometer,
            "fuel_gauge": fuel_gauge,
            "average_fuel_mileage": average_fuel_mileage,
            "meter_battery12V": meter_battery12v,
            "tripA": trip_a,
            "tripB": trip_b,
            "average_speed": average_speed,
            "outer_air_temperature": outer_air_temperature,
            "range_symbol": range_symbol,
            "range": range_value,
            "fuel_consumption": fuel_consumption,
            "total_time": total_time,
        }
    )

    for key, is_supported in supported.items():
        if not is_supported and key in out:
            out[key] = None
    return out


def parse_riding_log_ext(
    data: bytes, cfg: dict, info_flags: dict[str, int] | None = None
) -> dict[str, float | int | str | None]:
    """Parse frame 0x45 (riding-log extended metrics)."""
    out: dict[str, float | int | str | None] = {"frame": "0x45"}
    supported = cfg.get("supported_fields", {})
    config_flags = cfg.get("info_config_flags", {})

    def gate(flag: str | tuple[str, ...], expected: int) -> bool:
        keys = (flag,) if isinstance(flag, str) else flag
        value: int | None = None
        for key in keys:
            if info_flags and key in info_flags and isinstance(info_flags[key], int):
                value = info_flags[key]
                break
        if value is None:
            for key in keys:
                if key in config_flags and isinstance(config_flags[key], int):
                    value = config_flags[key]
                    break
        # If we do not know the gate flag, parse opportunistically.
        return value is None or value == expected

    total_distance_traveled: float | None = None
    if len(data) > 10 and gate("total_distance_traveled", 0):
        raw = (
            ((data[7] & 0xFF) << 24)
            | ((data[8] & 0xFF) << 16)
            | ((data[9] & 0xFF) << 8)
            | (data[10] & 0xFF)
        )
        total_distance_traveled = raw * 0.1

    engine_fuel_rate: float | None = None
    if len(data) > 12 and gate("engine_fuel_rate", 0):
        raw = ((data[11] & 0xFF) << 8) | (data[12] & 0xFF)
        engine_fuel_rate = raw * 0.02

    water_temperature: int | None = None
    if len(data) > 17 and gate("engine_water_temperature", 1):
        raw = data[17] & 0xFF
        water_temperature = None if raw == 0xFF else raw - 40

    oil_temperature: int | None = None
    if len(data) > 19 and gate("engine_oil_temperature", 1):
        raw = data[19] & 0xFF
        oil_temperature = None if raw == 0xFF else raw - 60

    inlet_air_temperature: int | None = None
    if len(data) > 20 and gate("inlet_air_temperature", 1):
        raw = data[20] & 0xFF
        inlet_air_temperature = None if raw == 0xFF else raw - 40

    instant_fuel_consumption: float | None = None
    if len(data) > 28 and gate("instant_fuel_consumption", 0):
        raw = ((data[27] & 0x03) << 8) | (data[28] & 0xFF)
        instant_fuel_consumption = raw * 0.1

    tire_pressure_fr: float | None = None
    tire_pressure_rr: float | None = None
    air_pressure_drop_fr: int | None = None
    air_pressure_drop_rr: int | None = None
    low_battery_voltage_fr: int | None = None
    low_battery_voltage_rr: int | None = None

    if len(data) > 49:
        tpms_disabled = bool(data[45] & 0x01) or bool(data[46] & 0x01)
        front_raw = data[47] & 0xFF
        rear_raw = data[48] & 0xFF

        if not tpms_disabled and front_raw != 0xFF:
            tire_pressure_fr = (front_raw * 1.373) + 100.0
        if not tpms_disabled and rear_raw != 0xFF:
            tire_pressure_rr = (rear_raw * 1.373) + 100.0

        if not tpms_disabled:
            warn = data[49] & 0xFF
            air_pressure_drop_fr = warn & 0x01
            air_pressure_drop_rr = (warn >> 1) & 0x01
            low_battery_voltage_fr = (warn >> 2) & 0x01
            low_battery_voltage_rr = (warn >> 3) & 0x01

    odometer: int | None = None
    if len(data) > 59 and gate("odometer", 0):
        odometer = (
            ((data[57] & 0x0F) << 16)
            | ((data[58] & 0xFF) << 8)
            | (data[59] & 0xFF)
        )

    out.update(
        {
            "total_distance_traveled": total_distance_traveled,
            "engine_fuel_rate": engine_fuel_rate,
            "water_temperature": water_temperature,
            "oil_temperature": oil_temperature,
            "inlet_air_temperature": inlet_air_temperature,
            "instant_fuel_consumption": instant_fuel_consumption,
            "tire_pressure_fr": tire_pressure_fr,
            "tire_pressure_rr": tire_pressure_rr,
            "air_pressure_drop_fr": air_pressure_drop_fr,
            "air_pressure_drop_rr": air_pressure_drop_rr,
            "low_battery_voltage_fr": low_battery_voltage_fr,
            "low_battery_voltage_rr": low_battery_voltage_rr,
            "odometer": odometer,
        }
    )

    for key, is_supported in supported.items():
        if not is_supported and key in out:
            out[key] = None
    return out


def _decode_u16_scaled_with_gate(
    data: bytes,
    *,
    gate_a: int,
    gate_b: int,
    hi: int,
    lo: int,
    scale: float,
) -> float | None:
    """Decode a big-endian u16 with a simple sentinel gate."""
    if len(data) <= max(gate_a, gate_b, hi, lo):
        return None
    if (data[gate_a] & 0xFF) == 0xFF or (data[gate_b] & 0xFF) == 0xFF:
        return None
    raw = ((data[hi] & 0xFF) << 8) | (data[lo] & 0xFF)
    return raw * scale


def _decode_centered_axis_with_gate(
    data: bytes,
    *,
    gate_a: int,
    gate_b: int,
    hi: int,
    lo: int,
    span: float,
) -> float | None:
    """Decode a centered axis value using app-matching scaling."""
    if len(data) <= max(gate_a, gate_b, hi, lo):
        return None
    if (data[gate_a] & 0xFF) == 0xFF or (data[gate_b] & 0xFF) == 0xFF:
        return None
    raw = ((data[hi] & 0xFF) << 8) | (data[lo] & 0xFF)
    if raw == 0:
        return None
    return (raw * span / 32768.0) - span


def parse_riding_log_high(data: bytes, cfg: dict) -> dict[str, float | str | None]:
    """Parse frame 0x4B (riding-log high-rate dynamics)."""
    out: dict[str, float | str | None] = {"frame": "0x4B"}
    supported = cfg.get("supported_fields", {})

    out.update(
        {
            "rr_suspension_stroke": _decode_u16_scaled_with_gate(
                data, gate_a=5, gate_b=6, hi=7, lo=8, scale=0.015625
            ),
            "fr_suspension_stroke": _decode_u16_scaled_with_gate(
                data, gate_a=5, gate_b=6, hi=9, lo=10, scale=0.015625
            ),
            "rr_suspension_stroke_vp": _decode_u16_scaled_with_gate(
                data, gate_a=5, gate_b=6, hi=11, lo=12, scale=0.001
            ),
            "fr_suspension_stroke_vp": _decode_u16_scaled_with_gate(
                data, gate_a=5, gate_b=6, hi=13, lo=14, scale=0.001
            ),
            "ay_psip1": _decode_centered_axis_with_gate(
                data, gate_a=15, gate_b=16, hi=18, lo=17, span=163.84
            ),
            "ay": _decode_centered_axis_with_gate(
                data, gate_a=15, gate_b=16, hi=22, lo=21, span=4.1768
            ),
            "ax_psip3": _decode_centered_axis_with_gate(
                data, gate_a=25, gate_b=26, hi=28, lo=27, span=163.84
            ),
            "ax": _decode_centered_axis_with_gate(
                data, gate_a=25, gate_b=26, hi=32, lo=31, span=4.1768
            ),
            "az_psip2": _decode_centered_axis_with_gate(
                data, gate_a=35, gate_b=36, hi=38, lo=37, span=163.84
            ),
            "az": _decode_centered_axis_with_gate(
                data, gate_a=35, gate_b=36, hi=42, lo=41, span=4.1768
            ),
        }
    )

    for key, is_supported in supported.items():
        if not is_supported and key in out:
            out[key] = None
    return out


def parse_general_setting_capability(
    data: bytes,
) -> dict[str, int | str | bool | None]:
    """Parse frame 0x1A (general-setting capability/config flags)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x1A"}
    if len(data) < 15:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    # Mirrors Ble5Value.b parsing in app code (ug/a.java case 2).
    shift_lamp_type = (data[7] & 0xC0) >> 6
    shift_lamp_level_max = data[8] & 0xFF
    shift_lamp_level_min = data[9] & 0xFF

    day_flag = (data[10] & 0xC0) >> 6
    month_flag = (data[10] & 0x30) >> 4
    year_flag = (data[10] & 0x0C) >> 2
    hour_flag = data[10] & 0x03
    minute_flag = (data[11] & 0xC0) >> 6
    second_flag = (data[11] & 0x30) >> 4

    meter_indication_capability = data[11] & 0x0F
    navi_control_point_capability = (data[12] & 0xF0) >> 4
    meter_indicator_subcap_1 = (data[12] & 0x0C) >> 2
    meter_indicator_subcap_2 = data[12] & 0x03
    meter_indicator_subcap_3 = (data[13] & 0xC0) >> 6
    meter_indicator_subcap_4 = (data[13] & 0x30) >> 4

    # Mirrors Ble5Value.b.f10977p semantics in app:
    # retry_required = ((b5 != 0xFF or b6 != 0xFF) and ((b14 & 0x01) == 0))
    # app considers valid/usable when retry_required is False.
    config_retry_required = (
        (((data[5] & 0xFF) != 0xFF) or ((data[6] & 0xFF) != 0xFF))
        and ((data[14] & 0x01) == 0)
    )
    config_valid = not config_retry_required

    shift_lamp_level_supported = (
        config_valid
        and 1 <= shift_lamp_level_min <= 61
        and 1 <= shift_lamp_level_max <= 61
        and shift_lamp_level_min <= shift_lamp_level_max
    )

    out.update(
        {
            "config_valid": config_valid,
            "config_retry_required": config_retry_required,
            "shift_lamp_type": shift_lamp_type,
            "shift_lamp_level_min": shift_lamp_level_min,
            "shift_lamp_level_max": shift_lamp_level_max,
            "shift_lamp_level_supported": shift_lamp_level_supported,
            "supports_day_setting": day_flag == 0,
            "supports_month_setting": month_flag == 0,
            "supports_year_setting": year_flag == 0,
            "supports_hour_setting": hour_flag == 0,
            "supports_minute_setting": minute_flag == 0,
            "supports_second_setting": second_flag == 0,
            "meter_indication_capability": meter_indication_capability,
            "navi_control_point_capability": navi_control_point_capability,
            "meter_indicator_subcap_1": meter_indicator_subcap_1,
            "meter_indicator_subcap_2": meter_indicator_subcap_2,
            "meter_indicator_subcap_3": meter_indicator_subcap_3,
            "meter_indicator_subcap_4": meter_indicator_subcap_4,
        }
    )
    return out


def parse_service_indicator(
    data: bytes, cfg: dict, common_flags: dict[str, int] | None = None
) -> dict[str, int | str | bool | None]:
    """Parse frame 0x1E (service indicator / maintenance status)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x1E"}
    if len(data) < 35:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["related_command"] = data[3] & 0xFF

    config_flags = cfg.get("common_service_config_flags", {})

    def _flag(name: str) -> int | None:
        if common_flags and isinstance(common_flags.get(name), int):
            return common_flags[name]
        value = config_flags.get(name)
        if isinstance(value, int):
            return value
        return None

    def _gate_zero(flag: str) -> bool:
        value = _flag(flag)
        return value is None or value == 0

    def _gate_capability(flag: str) -> bool:
        value = _flag(flag)
        return value is None or value in (0, 1)

    def _decode_month(byte_val: int) -> int | None:
        month = byte_val & 0x0F
        return month if 1 <= month <= 12 else None

    def _decode_day(byte_val: int) -> int | None:
        day = byte_val & 0x3F
        return day if 1 <= day <= 31 else None

    def _decode_year(byte_val: int) -> int | None:
        return None if byte_val == 0xFF else 2000 + (byte_val & 0x7F)

    def _decode_dist(hi_idx: int, mid_idx: int, lo_idx: int) -> int | None:
        if (data[hi_idx] & 0xFF) == 0xFF:
            return None
        return (
            ((data[hi_idx] & 0x0F) << 16)
            | ((data[mid_idx] & 0xFF) << 8)
            | (data[lo_idx] & 0xFF)
        )

    def _decode_notify(byte_val: int) -> int | None:
        return None if byte_val == 0xFF else ((byte_val & 0xF0) >> 4)

    kawasaki_service_setting_capability = (
        (data[7] & 0xFF) if _gate_capability("kawasaki_service_setting_capability") else None
    )
    kawasaki_service_notify = (
        _decode_notify(data[8]) if _gate_zero("kawasaki_service_notify") else None
    )
    kawasaki_service_month = (
        _decode_month(data[8]) if _gate_zero("kawasaki_service_month") else None
    )
    kawasaki_service_day = (
        _decode_day(data[9]) if _gate_zero("kawasaki_service_day") else None
    )
    kawasaki_service_year = (
        _decode_year(data[10]) if _gate_zero("kawasaki_service_year") else None
    )
    kawasaki_service_distance = (
        _decode_dist(12, 13, 14) if _gate_zero("kawasaki_service_distance") else None
    )

    rider_setting_capability = (
        (data[17] & 0xFF) if _gate_capability("user_setting_capability") else None
    )
    rider_setting_notify = (
        _decode_notify(data[18]) if _gate_zero("user_setting_notify") else None
    )
    rider_setting_month = (
        _decode_month(data[18]) if _gate_zero("user_setting_month") else None
    )
    rider_setting_day = (
        _decode_day(data[19]) if _gate_zero("user_setting_day") else None
    )
    rider_setting_year = (
        _decode_year(data[20]) if _gate_zero("user_setting_year") else None
    )
    rider_setting_distance = (
        _decode_dist(22, 23, 24) if _gate_zero("user_setting_distance") else None
    )

    oil_change_setting_capability = (
        (data[27] & 0xFF) if _gate_capability("oil_change_setting_capability") else None
    )
    oil_change_notify = (
        _decode_notify(data[28]) if _gate_zero("oil_change_notify") else None
    )
    oil_change_month = (
        _decode_month(data[28]) if _gate_zero("oil_change_month") else None
    )
    oil_change_day = (
        _decode_day(data[29]) if _gate_zero("oil_change_day") else None
    )
    oil_change_year = (
        _decode_year(data[30]) if _gate_zero("oil_change_year") else None
    )
    oil_change_distance = (
        _decode_dist(32, 33, 34) if _gate_zero("oil_change_distance") else None
    )

    out.update(
        {
            "kawasaki_service_setting_capability": kawasaki_service_setting_capability,
            "kawasaki_service_notify": kawasaki_service_notify,
            "kawasaki_service_month": kawasaki_service_month,
            "kawasaki_service_day": kawasaki_service_day,
            "kawasaki_service_year": kawasaki_service_year,
            "kawasaki_service_distance": kawasaki_service_distance,
            "rider_setting_capability": rider_setting_capability,
            "rider_setting_notify": rider_setting_notify,
            "rider_setting_month": rider_setting_month,
            "rider_setting_day": rider_setting_day,
            "rider_setting_year": rider_setting_year,
            "rider_setting_distance": rider_setting_distance,
            "oil_change_setting_capability": oil_change_setting_capability,
            "oil_change_notify": oil_change_notify,
            "oil_change_month": oil_change_month,
            "oil_change_day": oil_change_day,
            "oil_change_year": oil_change_year,
            "oil_change_distance": oil_change_distance,
            "kawasaki_service_supported": _gate_capability(
                "kawasaki_service_setting_capability"
            )
            and _gate_zero("kawasaki_service_notify"),
            "rider_setting_supported": _gate_capability("user_setting_capability")
            and _gate_zero("user_setting_notify"),
            "oil_change_supported": _gate_capability("oil_change_setting_capability")
            and _gate_zero("oil_change_notify"),
        }
    )
    return out


def parse_vehicle_settings(
    data: bytes,
    cfg: dict,
    tuning_flags: dict[str, int] | None = None,
) -> dict[str, int | str | None]:
    """Parse frame 0x48 (vehicle settings / tuning status)."""
    out: dict[str, int | str | None] = {"frame": "0x48"}
    if len(data) < 20:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["related_command"] = data[3] & 0xFF

    config_flags = cfg.get("tuning_config_flags", {})

    def _flag(name: str) -> int | None:
        if tuning_flags and isinstance(tuning_flags.get(name), int):
            return tuning_flags[name]
        value = config_flags.get(name)
        if isinstance(value, int):
            return value
        return None

    def _gate_01(name: str) -> bool:
        value = _flag(name)
        return value is None or value in (0, 1)

    def _gate_012(name: str) -> bool:
        value = _flag(name)
        return value is None or value in (0, 1, 2)

    def _gate_zero(name: str) -> bool:
        value = _flag(name)
        return value is None or value == 0

    meter_tuning_capability: int | None = None
    if len(data) > 7 and _gate_01("tuning_capability_meter"):
        raw = data[7] & 0xFF
        meter_tuning_capability = None if raw == 0xFF else raw

    ecu_tuning_capability: int | None = None
    if len(data) > 17 and _gate_01("tuning_capability_fiEcu"):
        raw = data[17] & 0xFF
        ecu_tuning_capability = None if raw == 0xFF else raw

    ktrc: int | None = None
    riding_mode: int | None = None
    if len(data) > 18 and (data[18] & 0xFF) != 0xFF:
        if _gate_012("ktrc"):
            ktrc = (data[18] & 0x78) >> 3
        if _gate_01("riding_mode"):
            riding_mode = data[18] & 0x07

    kqs: int | None = None
    kebc: int | None = None
    power: int | None = None
    if len(data) > 19 and (data[19] & 0xFF) != 0xFF:
        if _gate_zero("kqs"):
            kqs = (data[19] & 0x60) >> 5
        if _gate_zero("kebc"):
            kebc = (data[19] & 0x0C) >> 2
        if _gate_01("power"):
            power = data[19] & 0x03

    kecs_preload_mode: int | None = None
    kecs_mode: int | None = None
    if len(data) > 10 and (data[10] & 0xFF) != 0xFF:
        if _gate_zero("kecs_preload_mode"):
            kecs_preload_mode = (data[10] & 0x38) >> 3
        if _gate_zero("kecs_mode"):
            kecs_mode = data[10] & 0x07

    kecs_load_adjustment: int | None = None
    if len(data) > 11 and (data[11] & 0xFF) != 0xFF and _gate_zero("kecs_load_adjustment"):
        kecs_load_adjustment = data[11] & 0x0F

    kecs_damping_fr_com: int | None = None
    kecs_damping_fr_ten: int | None = None
    if len(data) > 12 and (data[12] & 0xFF) != 0xFF:
        if _gate_zero("kecs_damping_frCom"):
            kecs_damping_fr_com = (data[12] & 0xF0) >> 4
        if _gate_zero("kecs_damping_frTen"):
            kecs_damping_fr_ten = data[12] & 0x0F

    kecs_damping_rr_com: int | None = None
    kecs_damping_rr_ten: int | None = None
    if len(data) > 13 and (data[13] & 0xFF) != 0xFF:
        if _gate_zero("kecs_damping_rrCom"):
            kecs_damping_rr_com = (data[13] & 0xF0) >> 4
        if _gate_zero("kecs_damping_rrTen"):
            kecs_damping_rr_ten = data[13] & 0x0F

    out.update(
        {
            "meter_tuning_capability": meter_tuning_capability,
            "ecu_tuning_capability": ecu_tuning_capability,
            "ktrc": ktrc,
            "riding_mode": riding_mode,
            "kqs": kqs,
            "kebc": kebc,
            "power": power,
            "kecs_preload_mode": kecs_preload_mode,
            "kecs_mode": kecs_mode,
            "kecs_load_adjustment": kecs_load_adjustment,
            "kecs_damping_frCom": kecs_damping_fr_com,
            "kecs_damping_frTen": kecs_damping_fr_ten,
            "kecs_damping_rrCom": kecs_damping_rr_com,
            "kecs_damping_rrTen": kecs_damping_rr_ten,
        }
    )

    decoded_names = [
        name
        for name in (
            "meter_tuning_capability",
            "ecu_tuning_capability",
            "ktrc",
            "riding_mode",
            "kqs",
            "kebc",
            "power",
            "kecs_preload_mode",
            "kecs_mode",
            "kecs_load_adjustment",
            "kecs_damping_frCom",
            "kecs_damping_frTen",
            "kecs_damping_rrCom",
            "kecs_damping_rrTen",
        )
        if out.get(name) is not None
    ]
    out["decoded_count"] = len(decoded_names)
    out["decoded_fields"] = ",".join(decoded_names) if decoded_names else None
    return out


def parse_general_settings(
    data: bytes, capability: dict[str, int | str | bool | None] | None = None
) -> dict[str, int | str | bool | None]:
    """Parse frame 0x1B (general settings / time sync)."""
    out: dict[str, str | int | None] = {"frame": "0x1B"}
    if len(data) < 15:
        out["error"] = "short"
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["related_command"] = data[3] & 0xFF

    result_code_raw = data[7] & 0xFF
    out["result_code"] = None if result_code_raw == 0xFF else result_code_raw

    shift_status_raw = (data[8] >> 6) & 0x03
    shift_level_raw = data[8] & 0x3F
    if (data[8] & 0xFF) == 0xFF:
        out["shift_lamp_status"] = None
        out["shift_lamp_level"] = None
        out["shift_lamp_rpm"] = None
    else:
        out["shift_lamp_status"] = shift_status_raw
        out["shift_lamp_level"] = shift_level_raw if 1 <= shift_level_raw <= 61 else None
        out["shift_lamp_rpm"] = (
            ((shift_level_raw - 1) * 250 + 3000) if 1 <= shift_level_raw <= 61 else None
        )

    day_raw = data[9] & 0x3F
    month_raw = data[10] & 0x0F
    year_raw = data[11] & 0xFF
    hour_raw = data[12] & 0x1F
    minute_raw = data[13] & 0x3F
    second_raw = data[14] & 0x3F

    out["day"] = day_raw if 1 <= day_raw <= 31 else None
    out["month"] = month_raw if 1 <= month_raw <= 12 else None
    out["year"] = (2000 + year_raw) if year_raw != 0xFF else None
    out["hour"] = hour_raw if hour_raw <= 23 else None
    out["minute"] = minute_raw if minute_raw <= 59 else None
    out["second"] = second_raw if second_raw <= 59 else None

    if capability:
        if capability.get("shift_lamp_level_supported") is False:
            out["shift_lamp_status"] = None
            out["shift_lamp_level"] = None
            out["shift_lamp_rpm"] = None
        if capability.get("supports_day_setting") is False:
            out["day"] = None
        if capability.get("supports_month_setting") is False:
            out["month"] = None
        if capability.get("supports_year_setting") is False:
            out["year"] = None
        if capability.get("supports_hour_setting") is False:
            out["hour"] = None
        if capability.get("supports_minute_setting") is False:
            out["minute"] = None
        if capability.get("supports_second_setting") is False:
            out["second"] = None
    return out


def parse_ack(data: bytes) -> dict[str, int | str | None]:
    """Parse generic ACK frame (0x20)."""
    out: dict[str, int | str | None] = {"frame": "0x20"}
    if len(data) > 1:
        out["payload_len"] = data[1] & 0xFF
    if len(data) > 2:
        out["sequence"] = data[2] & 0xFF
    if len(data) > 3:
        ack_command = data[3] & 0xFF
        out["ack_command"] = ack_command
        out["ack_command_name"] = _frame_name(ack_command)
    if len(data) > 7:
        out["result_code"] = data[7] & 0xFF
    elif len(data) > 4:
        out["result_code"] = data[4] & 0xFF
    result_code = out.get("result_code")
    if isinstance(result_code, int):
        out["result_text"] = _ack_result_text(result_code)

    ack_command = out.get("ack_command")
    if ack_command == FRAME_PHONE_MODEL:
        text, chunk_ids = _parse_text_chunks_by_0x05(data, start_index=5)
        out["phone_model_text"] = text
        out["phone_model_chunk_ids"] = chunk_ids

    if ack_command == FRAME_METER_INDICATION_INIT:
        if len(data) > 5:
            out["meter_indication_block_id"] = data[5] & 0xFF
        if len(data) > 6:
            out["meter_indication_command_id"] = data[6] & 0xFF
        if len(data) > 8:
            out["meter_indication_param_1"] = data[8] & 0xFF
        if len(data) > 10:
            out["meter_indication_param_2"] = ((data[9] & 0xFF) << 8) | (
                data[10] & 0xFF
            )
        if len(data) > 12:
            out["meter_indication_param_3"] = ((data[11] & 0xFF) << 8) | (
                data[12] & 0xFF
            )
        if len(data) > 14:
            out["meter_indication_param_4"] = ((data[13] & 0xFF) << 8) | (
                data[14] & 0xFF
            )
    return out


def _parse_text_chunks_by_0x05(
    data: bytes, *, start_index: int = 5
) -> tuple[str | None, str | None]:
    """Parse repeating 0x05 <chunk_id> <8-byte-text> slots used by 0x0B/0x30."""
    chunks: dict[int, str] = {}
    i = start_index
    while i + 1 < len(data):
        if data[i] != 0x05:
            i += 1
            continue

        chunk_id = data[i + 1] & 0xFF
        chunk_end = min(i + 10, len(data))
        chunk_text = (
            bytes(data[i + 2 : chunk_end])
            .decode("utf-8", errors="ignore")
            .replace("\x00", "")
            .replace("\xff", "")
            .strip()
        )
        if chunk_text:
            chunks[chunk_id] = chunk_text
        i += 10

    ordered_ids = sorted(chunks.keys())
    if not ordered_ids:
        return None, None

    chunk_ids = ",".join(f"0x{chunk_id:02X}" for chunk_id in ordered_ids)
    text = "".join(chunks[chunk_id] for chunk_id in ordered_ids)
    return text or None, chunk_ids


def parse_phone_model(data: bytes) -> dict[str, int | str | None]:
    """Parse frame 0x0B (phone/client model text chunks)."""
    out: dict[str, int | str | None] = {"frame": "0x0B"}
    if len(data) > 1:
        out["payload_len"] = data[1] & 0xFF
    if len(data) > 2:
        out["sequence"] = data[2] & 0xFF
    if len(data) > 3:
        out["reserved_3"] = data[3] & 0xFF
    if len(data) > 4:
        out["reserved_4"] = data[4] & 0xFF

    text, chunk_ids = _parse_text_chunks_by_0x05(data, start_index=5)
    out["text"] = text
    out["chunk_ids"] = chunk_ids
    return out


def parse_emc_info(data: bytes) -> dict[str, int | str | bool | None]:
    """Parse frame 0x42 (EMC vehicle information; format varies by model)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x42", "raw_len": len(data)}
    if len(data) == 3 and data[1] == 0x00:
        # App requests 0x42 with [0x42, 0x00, 0x01].
        out["packet_type"] = "request_command"
        out["request_tail"] = data[2] & 0xFF
        return out

    if len(data) > 1:
        out["payload_len"] = data[1] & 0xFF
    if len(data) > 2:
        out["sequence"] = data[2] & 0xFF
    if len(data) > 3:
        out["related_command"] = data[3] & 0xFF

    # On supported EV/HEV models, app parses 0x42 through Ble5Value.u,
    # which uses the same bitfield layout as the 0x1D common-service config.
    if len(data) >= 15 and (data[1] & 0xFF) == 0x0C:
        service_cfg = parse_common_service_config_flags(data)
        service_cfg.pop("frame", None)
        out.update(service_cfg)
        out["packet_type"] = "service_indicator_config_like"
        return out

    if len(data) >= 8 and data[5] == 0x05:
        out["packet_type"] = "block_result"
        out["block_id"] = data[6] & 0xFF
        out["block_value"] = data[7] & 0xFF
        return out

    text, chunk_ids = _parse_text_chunks_by_0x05(data, start_index=5)
    if text or chunk_ids:
        out["packet_type"] = "text_chunks"
        out["text"] = text
        out["chunk_ids"] = chunk_ids
        return out

    out["packet_type"] = "raw_or_unknown"
    return out


def parse_meter_indication_init(data: bytes) -> dict[str, int | str | bool | None]:
    """Parse frame 0x08 (meter indication init/profile command)."""
    out: dict[str, int | str | bool | None] = {"frame": "0x08"}
    if len(data) < 8:
        out["error"] = "short"
        out["raw_len"] = len(data)
        return out

    out["payload_len"] = data[1] & 0xFF
    out["sequence"] = data[2] & 0xFF
    out["reserved_3"] = data[3] & 0xFF
    out["reserved_4"] = data[4] & 0xFF
    out["block_id"] = data[5] & 0xFF
    out["command_id"] = data[6] & 0xFF
    out["enabled"] = (data[7] & 0xFF) == 0x01

    if len(data) > 8:
        out["param_1"] = data[8] & 0xFF
    if len(data) > 10:
        out["param_2"] = ((data[9] & 0xFF) << 8) | (data[10] & 0xFF)
    if len(data) > 12:
        out["param_3"] = ((data[11] & 0xFF) << 8) | (data[12] & 0xFF)
    if len(data) > 14:
        out["param_4"] = ((data[13] & 0xFF) << 8) | (data[14] & 0xFF)

    out["is_default_profile"] = (
        out.get("payload_len") == 0x0C
        and out.get("block_id") == 0x0A
        and out.get("command_id") == 0x08
        and out.get("enabled") is True
        and out.get("param_1") == 120
        and out.get("param_2") == 1000
        and out.get("param_3") == 200
        and out.get("param_4") == 100
    )
    return out


def parse_model_info(data: bytes) -> dict[str, str | int | None]:
    """Parse model info frame (0x03), including VIN-style identity segments."""
    out: dict[str, str | int | None] = {"frame": "0x03"}
    if len(data) < 8:
        out["raw_len"] = len(data)
        return out

    # Parse TLV-like chunks seen in app traffic: 0x02 0x71/0x72/0x73 <ASCII...>.
    tlv_chunks: dict[int, str] = {}
    i = 5
    while i + 2 < len(data):
        if data[i] != 0x02:
            i += 1
            continue
        tag = data[i + 1] & 0xFF
        end = i + 2
        while end < len(data) and data[end] not in (0x02, 0xFF):
            end += 1
        chunk = (
            bytes(data[i + 2 : end])
            .decode("ascii", errors="ignore")
            .replace("\x00", "")
            .strip()
        )
        if chunk:
            tlv_chunks[tag] = chunk
        i = end

    model_code = tlv_chunks.get(0x71)
    serial_code = tlv_chunks.get(0x72)
    suffix_code = tlv_chunks.get(0x73)

    if model_code:
        out["vin_part_71"] = model_code
    if serial_code:
        out["vin_part_72"] = serial_code
    if suffix_code:
        out["vin_part_73"] = suffix_code

    model_name: str | None = model_code
    vin: str | None = None
    if model_code and serial_code:
        candidate = f"{model_code}{serial_code}{suffix_code or ''}".strip()
        if len(candidate) in {13, 17}:
            vin = candidate

    if not model_name and len(data) >= 33:
        stitched = bytearray()
        stitched.extend(data[2:8])
        stitched.extend(data[8:14])
        stitched.extend(data[27:33])
        stitched_ascii = (
            bytes(stitched)
            .decode("ascii", errors="ignore")
            .replace("\x00", "")
            .replace("\xff", "")
            .strip()
        )
        model_name = stitched_ascii or None
        if not vin and len(stitched_ascii) in {13, 17}:
            vin = stitched_ascii

    out["model_name"] = model_name or None
    out["vin"] = vin
    return out


def parse_startup_status(data: bytes) -> dict[str, int | str | None]:
    """Parse generic startup/status frames we currently don't fully decode."""
    out: dict[str, int | str | None] = {"frame": f"0x{data[0]:02X}"}
    if len(data) > 1:
        out["payload_len"] = data[1] & 0xFF
    if len(data) > 2:
        out["sequence"] = data[2] & 0xFF
    if len(data) > 3:
        out["related_command"] = data[3] & 0xFF
    if len(data) > 7 and len(data) >= 8 and data[5] == 0x05:
        out["block_id"] = data[6] & 0xFF
        out["block_value"] = data[7] & 0xFF
    return out


def parse_status_report(data: bytes) -> dict[str, int | str | None]:
    """Parse frame 0x30 status/report blocks and text chunks."""
    out: dict[str, int | str | None] = {"frame": "0x30"}
    if len(data) > 1:
        out["payload_len"] = data[1] & 0xFF
    if len(data) > 2:
        out["sequence"] = data[2] & 0xFF
    if len(data) > 3:
        out["related_command"] = data[3] & 0xFF

    payload_len = data[1] & 0xFF if len(data) > 1 else None

    # 15-byte status/result block format:
    # 30 0C <seq> FF FF 05 <block_id> <result> ...
    if len(data) >= 8 and payload_len == 0x0C and data[5] == 0x05:
        block_id = data[6] & 0xFF
        result_code = data[7] & 0xFF
        out["status_type"] = "block_result"
        out["block_id"] = block_id
        out["block_name"] = _frame_name(block_id)
        out["result_code"] = result_code
        out["result_text"] = _ack_result_text(result_code)
        return out

    # 35-byte text chunk format:
    # 30 20 <seq> FF FF 05 01 <8 bytes> 05 02 <8 bytes> ...
    if len(data) >= 35 and payload_len == 0x20:
        chunks: dict[int, str] = {}
        i = 5
        while i + 9 < len(data):
            if data[i] != 0x05:
                i += 1
                continue
            chunk_id = data[i + 1] & 0xFF
            chunk = (
                bytes(data[i + 2 : i + 10])
                .decode("utf-8", errors="ignore")
                .replace("\x00", "")
                .replace("\xff", "")
                .strip()
            )
            if chunk:
                chunks[chunk_id] = chunk
            i += 10

        ordered_ids = sorted(chunks.keys())
        if ordered_ids:
            out["chunk_ids"] = ",".join(f"0x{chunk_id:02X}" for chunk_id in ordered_ids)
        text = "".join(chunks[chunk_id] for chunk_id in ordered_ids)
        out["status_type"] = "text_chunks"
        out["text"] = text or None
        return out

    out["status_type"] = "generic"
    if len(data) > 7 and data[5] == 0x05:
        out["block_id"] = data[6] & 0xFF
        out["block_value"] = data[7] & 0xFF
    return out
