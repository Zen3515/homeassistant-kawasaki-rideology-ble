"""Coordinator for Kawasaki BLE streaming."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from bleak import BleakError
from bleak_retry_connector import close_stale_connections_by_address

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .kawi_ble5_client import (
    FRAME_COMMON_SERVICE,
    FRAME_EMC_INFO,
    FRAME_GENERAL_SETTING_CAPABILITY,
    FRAME_MC_INFO,
    FRAME_MC_INFO_CONFIG,
    FRAME_METER_INDICATION_INIT,
    FRAME_MODEL_INFO,
    FRAME_PHONE_MODEL,
    FRAME_RIDING_LOG_EXT,
    FRAME_RIDING_LOG_HIGH,
    FRAME_RIDING_LOG_MID,
    FRAME_SERVICE_INDICATOR,
    FRAME_VEHICLE_SETTING_CONFIG,
    FRAME_VEHICLE_SETTINGS,
    KawiBle5Client,
)

_LOGGER = logging.getLogger(__name__)
RECONNECT_DELAY = 10.0


class KawasakiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Maintain a long-lived BLE connection and stream frames."""

    def __init__(
        self, hass: HomeAssistant, *, address: str, model: str, config: dict
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.address = address
        self.model = model
        self.config = config
        self.data: dict[str, Any] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._client: KawiBle5Client | None = None
        self._available = False
        self._unavailable_logged = False
        self._connection_attempt = 0
        self._frame_count = 0
        self._received_frame_count = 0
        self._last_frame_monotonic = 0.0
        self._last_mc_info_probe_monotonic = 0.0
        self._mc_info_probe_on_stale = bool(
            self.config.get("mc_info_probe_on_stale", True)
        )
        self._mc_info_stale_after_s = max(
            1.0, float(self.config.get("mc_info_stale_after_s", 20.0))
        )
        self._mc_info_probe_interval_s = max(
            1.0, float(self.config.get("mc_info_probe_interval_s", 20.0))
        )

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return self._available

    def _set_available(
        self,
        available: bool,
        *,
        reason: str | None = None,
    ) -> None:
        """Update availability and log state transitions once."""
        if available == self._available:
            return

        self._available = available
        self.hass.loop.call_soon_threadsafe(self.async_update_listeners)
        if available:
            if self._unavailable_logged:
                _LOGGER.info("Device is back online: %s", self.address)
                self._unavailable_logged = False
            else:
                _LOGGER.info("Connected to %s", self.address)
            return

        if self._unavailable_logged:
            return
        if reason:
            _LOGGER.info("Device is unavailable: %s (%s)", self.address, reason)
        else:
            _LOGGER.info("Device is unavailable: %s", self.address)
        self._unavailable_logged = True

    async def async_start(self) -> None:
        """Start the background BLE task."""
        if self._task:
            _LOGGER.debug("Background task already running for %s", self.address)
            return
        _LOGGER.debug("Starting background BLE task for %s", self.address)
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name=f"{DOMAIN}_{self.address}")

    async def async_stop(self) -> None:
        """Stop the background BLE task."""
        _LOGGER.debug("Stopping background BLE task for %s", self.address)
        self._stop_event.set()
        if self._client:
            await self._client.async_stop()
            self._client = None
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        _LOGGER.debug("Stopped background BLE task for %s", self.address)

    def _handle_frame(self, frame_id: int, parsed: dict | None, raw: bytes) -> None:
        self._received_frame_count += 1
        self._last_frame_monotonic = time.monotonic()

        stream_frame_ids = {
            FRAME_MC_INFO,
            FRAME_RIDING_LOG_MID,
            FRAME_RIDING_LOG_EXT,
            FRAME_RIDING_LOG_HIGH,
        }
        metadata_frame_ids = {
            FRAME_MODEL_INFO,
            FRAME_METER_INDICATION_INIT,
            FRAME_PHONE_MODEL,
            FRAME_GENERAL_SETTING_CAPABILITY,
            FRAME_MC_INFO_CONFIG,
            FRAME_COMMON_SERVICE,
            FRAME_EMC_INFO,
            FRAME_VEHICLE_SETTING_CONFIG,
            FRAME_VEHICLE_SETTINGS,
            FRAME_SERVICE_INDICATOR,
        }

        if not parsed or frame_id not in (stream_frame_ids | metadata_frame_ids):
            _LOGGER.debug(
                "Received frame 0x%02X parsed=%s raw_len=%s raw=%s",
                frame_id,
                parsed is not None,
                len(raw),
                raw.hex(),
            )
            return

        payload = dict(self.data)
        payload["last_seen"] = time.time()

        if frame_id in stream_frame_ids:
            self._frame_count += 1
            payload.update(parsed)

        if frame_id == FRAME_MODEL_INFO:
            payload["model_info"] = parsed
            vin = parsed.get("vin")
            if isinstance(vin, str) and vin:
                payload["vin"] = vin
            _LOGGER.debug(
                "Parsed frame 0x%02X model_name=%s vin=%s",
                frame_id,
                parsed.get("model_name"),
                parsed.get("vin"),
            )
        elif frame_id == FRAME_METER_INDICATION_INIT:
            payload["meter_indication_init"] = parsed
            _LOGGER.debug(
                (
                    "Parsed frame 0x%02X meter indication init block_id=0x%02X "
                    "command=0x%02X enabled=%s"
                ),
                frame_id,
                parsed.get("block_id", 0),
                parsed.get("command_id", 0),
                parsed.get("enabled"),
            )
        elif frame_id == FRAME_PHONE_MODEL:
            payload["phone_model"] = parsed
            _LOGGER.debug(
                "Parsed frame 0x%02X phone model text=%s",
                frame_id,
                parsed.get("text"),
            )
        elif frame_id == FRAME_EMC_INFO:
            payload["emc_info"] = parsed
            _LOGGER.debug(
                "Parsed frame 0x%02X EMC info packet_type=%s",
                frame_id,
                parsed.get("packet_type"),
            )
        elif frame_id == FRAME_GENERAL_SETTING_CAPABILITY:
            payload["general_setting_capability"] = parsed
            _LOGGER.debug(
                "Parsed frame 0x%02X general capability valid=%s shift_lamp_supported=%s",
                frame_id,
                parsed.get("config_valid"),
                parsed.get("shift_lamp_level_supported"),
            )
        elif frame_id == FRAME_MC_INFO_CONFIG:
            payload["mc_info_config"] = parsed
            _LOGGER.debug(
                "Parsed frame 0x%02X MC info config supported_count=%s unsupported_count=%s",
                frame_id,
                parsed.get("supported_count"),
                parsed.get("unsupported_count"),
            )
        elif frame_id == FRAME_COMMON_SERVICE:
            payload["common_service_config"] = parsed
            _LOGGER.debug(
                (
                    "Parsed frame 0x%02X common service config valid=%s "
                    "kawasaki_supported=%s rider_supported=%s oil_supported=%s"
                ),
                frame_id,
                parsed.get("config_valid"),
                parsed.get("kawasaki_service_supported"),
                parsed.get("rider_setting_supported"),
                parsed.get("oil_change_supported"),
            )
        elif frame_id == FRAME_VEHICLE_SETTING_CONFIG:
            payload["vehicle_setting_config"] = parsed
            _LOGGER.debug(
                "Parsed frame 0x%02X vehicle setting config supported_count=%s unsupported_count=%s",
                frame_id,
                parsed.get("supported_count"),
                parsed.get("unsupported_count"),
            )
        elif frame_id == FRAME_VEHICLE_SETTINGS:
            payload["vehicle_settings"] = parsed
            _LOGGER.debug(
                "Parsed frame 0x%02X vehicle settings decoded_count=%s",
                frame_id,
                parsed.get("decoded_count"),
            )
        elif frame_id == FRAME_SERVICE_INDICATOR:
            payload["service_maintenance"] = parsed
            _LOGGER.debug(
                (
                    "Parsed frame 0x%02X service maintenance kawasaki_supported=%s "
                    "rider_supported=%s oil_supported=%s"
                ),
                frame_id,
                parsed.get("kawasaki_service_supported"),
                parsed.get("rider_setting_supported"),
                parsed.get("oil_change_supported"),
            )
        elif frame_id == FRAME_MC_INFO:
            _LOGGER.debug(
                (
                    "Parsed frame 0x%02X count=%s ecu_battery12V=%s meter_battery12V=%s "
                    "odometer=%s fuel_gauge=%s"
                ),
                frame_id,
                self._frame_count,
                payload.get("ecu_battery12V"),
                payload.get("meter_battery12V"),
                payload.get("odometer"),
                payload.get("fuel_gauge"),
            )
        elif frame_id == FRAME_RIDING_LOG_MID:
            _LOGGER.debug(
                "Parsed frame 0x%02X count=%s rpm=%s speed=%s gear=%s throttle=%s",
                frame_id,
                self._frame_count,
                payload.get("rpm"),
                payload.get("wheel_kph"),
                payload.get("gear"),
                payload.get("throttle"),
            )
        elif frame_id == FRAME_RIDING_LOG_EXT:
            _LOGGER.debug(
                (
                    "Parsed frame 0x%02X count=%s water=%s oil=%s inlet=%s "
                    "tire_fr=%s tire_rr=%s odometer=%s"
                ),
                frame_id,
                self._frame_count,
                payload.get("water_temperature"),
                payload.get("oil_temperature"),
                payload.get("inlet_air_temperature"),
                payload.get("tire_pressure_fr"),
                payload.get("tire_pressure_rr"),
                payload.get("odometer"),
            )
        elif frame_id == FRAME_RIDING_LOG_HIGH:
            _LOGGER.debug(
                (
                    "Parsed frame 0x%02X count=%s rr_stroke=%s fr_stroke=%s "
                    "ay=%s ax=%s az=%s"
                ),
                frame_id,
                self._frame_count,
                payload.get("rr_suspension_stroke"),
                payload.get("fr_suspension_stroke"),
                payload.get("ay"),
                payload.get("ax"),
                payload.get("az"),
            )

        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, payload)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            self._connection_attempt += 1
            _LOGGER.debug(
                "Starting connection attempt %s for %s",
                self._connection_attempt,
                self.address,
            )
            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if not ble_device:
                self._set_available(False, reason="no connectable device found")
                _LOGGER.debug(
                    "No connectable device found for %s, retrying in %s seconds",
                    self.address,
                    RECONNECT_DELAY,
                )
                self.hass.loop.call_soon_threadsafe(
                    self.async_set_updated_data, dict(self.data)
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=RECONNECT_DELAY
                    )
                except TimeoutError:
                    continue
                break

            _LOGGER.debug(
                "Found connectable device for %s with name %s",
                self.address,
                ble_device.name,
            )
            client = KawiBle5Client(
                address=self.address,
                ble_device=ble_device,
                config=self.config,
                debug=bool(self.config.get("debug_frames", False)),
                log_1b=bool(self.config.get("log_1b", False)),
                on_frame=self._handle_frame,
            )
            self._client = client
            try:
                _LOGGER.debug("Closing stale connections for %s", self.address)
                await close_stale_connections_by_address(self.address)
                _LOGGER.debug("Connecting BLE client for %s", self.address)
                await client.async_start()
                self._frame_count = 0
                self._received_frame_count = 0
                self._last_frame_monotonic = 0.0
                self._last_mc_info_probe_monotonic = 0.0
                self._set_available(True)
                self.hass.loop.call_soon_threadsafe(
                    self.async_set_updated_data, dict(self.data)
                )
                _LOGGER.debug("Sending startup frame sequence to %s", self.address)
                await client.async_startup_sequence()

                monitor_count = 0
                while client.connected and not self._stop_event.is_set():
                    await asyncio.sleep(1)
                    monitor_count += 1
                    now_monotonic = time.monotonic()
                    frame_age_s = (
                        now_monotonic - self._last_frame_monotonic
                        if self._last_frame_monotonic > 0
                        else float("inf")
                    )

                    if monitor_count % 15 == 0:
                        _LOGGER.debug(
                            (
                                "Connection monitor for %s connected=%s frames=%s "
                                "received_frames=%s frame_age_s=%.1f stale_after_s=%.1f "
                                "stale_probe_enabled=%s"
                            ),
                            self.address,
                            client.connected,
                            self._frame_count,
                            self._received_frame_count,
                            frame_age_s,
                            self._mc_info_stale_after_s,
                            self._mc_info_probe_on_stale,
                        )

                    if not self._mc_info_probe_on_stale:
                        continue
                    if self._received_frame_count == 0:
                        continue

                    since_last_probe_s = (
                        now_monotonic - self._last_mc_info_probe_monotonic
                        if self._last_mc_info_probe_monotonic > 0
                        else float("inf")
                    )
                    if frame_age_s < self._mc_info_stale_after_s:
                        continue
                    if since_last_probe_s < self._mc_info_probe_interval_s:
                        continue

                    _LOGGER.debug(
                        (
                            "No BLE frames for %.1fs on %s; sending stale MC probe "
                            "(min_interval=%.1fs)"
                        ),
                        frame_age_s,
                        self.address,
                        self._mc_info_probe_interval_s,
                    )
                    with contextlib.suppress(Exception):
                        await client.async_request_mc_info()
                    self._last_mc_info_probe_monotonic = now_monotonic
            except TimeoutError as exc:
                _LOGGER.warning(
                    "BLE startup timed out for %s; reconnecting: %s",
                    self.address,
                    exc,
                )
            except (BleakError, OSError, RuntimeError) as exc:
                _LOGGER.debug("BLE error for %s: %s", self.address, exc)
            except Exception:
                _LOGGER.exception(
                    "Unexpected error while streaming from %s", self.address
                )
            finally:
                _LOGGER.debug("Stopping BLE client for %s", self.address)
                with contextlib.suppress(Exception):
                    await client.async_stop()
                self._client = None
                self._set_available(False, reason="connection closed")

            if self._stop_event.is_set():
                break
            _LOGGER.debug(
                "Waiting %s seconds before reconnect attempt for %s",
                RECONNECT_DELAY,
                self.address,
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=RECONNECT_DELAY)
            except TimeoutError:
                continue
