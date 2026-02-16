"""Sensors for Kawasaki BLE streaming."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    DEGREE,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL, DOMAIN, MODEL_NAMES
from .coordinator import KawasakiCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="status_fuel_injection",
        name="Fuel Injection Status",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rpm",
        name="Engine RPM",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="wheel_kph",
        name="Wheel Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="gear",
        name="Gear",
    ),
    SensorEntityDescription(
        key="throttle",
        name="Throttle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="lean_deg",
        name="Lean Angle",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
    ),
    SensorEntityDescription(
        key="accel_g",
        name="Acceleration",
        native_unit_of_measurement="g",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="total_distance_traveled",
        name="Total Distance Traveled",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ecu_battery12V",
        name="ECU Battery 12V",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="meter_battery12V",
        name="Meter Battery 12V",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="total_fuel_consumed",
        name="Total Fuel Consumed",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="fuel_gauge",
        name="Fuel Gauge Level",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="average_fuel_mileage",
        name="Average Fuel Mileage",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tripA",
        name="Trip A",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tripB",
        name="Trip B",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="average_speed",
        name="Average Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="outer_air_temperature",
        name="Outer Air Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="range_symbol",
        name="Range Symbol",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="range",
        name="Range",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="fuel_consumption",
        name="Fuel Consumption",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="total_time",
        name="Total Time",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="engine_fuel_rate",
        name="Engine Fuel Rate",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="water_temperature",
        name="Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="oil_temperature",
        name="Oil Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="inlet_air_temperature",
        name="Inlet Air Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="instant_fuel_consumption",
        name="Instant Fuel Consumption",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tire_pressure_fr",
        name="Front Tire Pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tire_pressure_rr",
        name="Rear Tire Pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="air_pressure_drop_fr",
        name="Front Tire Pressure Drop Alert",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="air_pressure_drop_rr",
        name="Rear Tire Pressure Drop Alert",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="low_battery_voltage_fr",
        name="Front TPMS Battery Low",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="low_battery_voltage_rr",
        name="Rear TPMS Battery Low",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rr_suspension_stroke",
        name="Rear Suspension Stroke",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="fr_suspension_stroke",
        name="Front Suspension Stroke",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rr_suspension_stroke_vp",
        name="Rear Suspension Stroke VP",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="fr_suspension_stroke_vp",
        name="Front Suspension Stroke VP",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ay_psip1",
        name="AY PSIP1",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ay",
        name="AY",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ax_psip3",
        name="AX PSIP3",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ax",
        name="AX",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="az_psip2",
        name="AZ PSIP2",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="az",
        name="AZ",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="odometer",
        name="Odometer",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kawasaki sensors from a config entry."""
    del hass
    coordinator: KawasakiCoordinator = entry.runtime_data
    address = entry.unique_id or entry.data.get(CONF_ADDRESS) or coordinator.address
    if not isinstance(address, str) or not address:
        address = coordinator.address

    model = entry.data.get(CONF_MODEL, coordinator.model)
    if not isinstance(model, str) or not model:
        model = coordinator.model
    model_name = MODEL_NAMES.get(model, model)

    supported = coordinator.config.get("supported_fields", {})
    entities: list[KawasakiSensor] = []
    created_keys: list[str] = []
    for description in SENSOR_DESCRIPTIONS:
        if description.key in supported and not supported[description.key]:
            _LOGGER.debug(
                "Skipping unsupported sensor key=%s for %s",
                description.key,
                address,
            )
            continue
        entities.append(
            KawasakiSensor(
                coordinator=coordinator,
                description=description,
                unique_id=f"{address}-{description.key}",
                address=address,
                name_prefix=model_name,
                model_name=model_name,
            )
        )
        created_keys.append(description.key)

    async_add_entities(entities)
    _LOGGER.debug(
        "Added %s sensors for %s with keys=%s",
        len(entities),
        address,
        created_keys,
    )


class KawasakiSensor(CoordinatorEntity[KawasakiCoordinator], SensorEntity):
    """Representation of a Kawasaki sensor."""

    def __init__(
        self,
        *,
        coordinator: KawasakiCoordinator,
        description: SensorEntityDescription,
        unique_id: str,
        address: str,
        name_prefix: str,
        model_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = unique_id
        self._address = address
        self._model_name = model_name
        self._attr_name = f"{name_prefix} {description.name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return dynamic device info aligned with HA device registry guidance."""
        info: dict[str, Any] = {
            "identifiers": {(DOMAIN, self._address)},
            "connections": {(CONNECTION_BLUETOOTH, self._address)},
            "manufacturer": "Kawasaki",
            "model": self._model_name,
            "model_id": self.coordinator.model,
            "name": f"Kawasaki {self._model_name}",
        }
        return DeviceInfo(**info)

    @property
    def native_value(self) -> int | float | str | None:
        """Return the current value."""
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return self.coordinator.available

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose VIN, service/maintenance data, and parsed support flags."""
        attrs: dict[str, Any] = {}
        data = self.coordinator.data

        vin = data.get("vin")
        if isinstance(vin, str) and vin:
            attrs["vin"] = vin

        service_maintenance = data.get("service_maintenance")
        if isinstance(service_maintenance, dict):
            service_attrs = {
                key: value
                for key, value in service_maintenance.items()
                if key not in {"frame", "payload_len", "sequence", "related_command"}
            }
            if service_attrs:
                attrs["service_maintenance"] = service_attrs

        supported_flags: dict[str, Any] = {}
        for group_key in (
            "general_setting_capability",
            "common_service_config",
            "mc_info_config",
            "vehicle_setting_config",
        ):
            group = data.get(group_key)
            if not isinstance(group, dict):
                continue
            group_attrs = {
                key: value
                for key, value in group.items()
                if key not in {"frame", "payload_len", "sequence", "related_command"}
            }
            if group_attrs:
                supported_flags[group_key] = group_attrs

        telemetry_supported = self.coordinator.config.get("supported_fields")
        if isinstance(telemetry_supported, dict):
            supported_flags["telemetry_supported_fields"] = telemetry_supported

        if supported_flags:
            attrs["supported_flags"] = supported_flags

        return attrs or None
