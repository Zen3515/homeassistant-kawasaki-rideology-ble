"""Config flow for Kawasaki BLE integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_MODEL, DOMAIN, MODEL_NAMES, NAME_PREFIXES


class KawasakiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kawasaki BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    @staticmethod
    def _matches_name(name: str | None) -> bool:
        if not name:
            return False
        lower = name.lower()
        return any(lower.startswith(prefix.lower()) for prefix in NAME_PREFIXES)

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        name = discovery_info.name or discovery_info.device.name
        if not self._matches_name(name):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        self._address = discovery_info.address
        self._name = name or discovery_info.address
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return await self.async_step_model()

        name = self._name or "Kawasaki"
        self._set_confirm_only()
        self.context["title_placeholders"] = {"name": name}
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._address = address
            self._name = self._discovered_devices.get(address, address)
            return await self.async_step_model()

        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            name = discovery_info.name or discovery_info.device.name
            if not self._matches_name(name):
                continue
            self._discovered_devices[address] = name or address

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )

    async def async_step_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the model for the discovered device."""
        if user_input is not None:
            model = user_input[CONF_MODEL]
            address = self._address
            if address is None:
                return self.async_abort(reason="no_devices_found")
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            name = self._name or MODEL_NAMES.get(model, model)
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: address, CONF_MODEL: model},
            )

        return self.async_show_form(
            step_id="model",
            data_schema=vol.Schema({vol.Required(CONF_MODEL): vol.In(MODEL_NAMES)}),
        )
