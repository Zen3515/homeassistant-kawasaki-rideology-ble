"""Config flow for Kawasaki BLE integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_current_scanners,
    async_discovered_service_info,
    async_scanner_by_source,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import (
    CONF_MODEL,
    CONF_PREFERRED_PROXY_SOURCE,
    DOMAIN,
    MODEL_NAMES,
    NAME_PREFIXES,
)

AUTO_PROXY_SOURCE = "__auto__"
AUTO_PROXY_LABEL = "Automatic (any available proxy)"


class KawasakiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kawasaki BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None
        self._preferred_proxy_source: str | None = None

    @staticmethod
    def _matches_name(name: str | None) -> bool:
        if not name:
            return False
        lower = name.lower()
        return any(lower.startswith(prefix.lower()) for prefix in NAME_PREFIXES)

    @staticmethod
    def _proxy_choice_label(source: str, scanner_name: str | None) -> str:
        if scanner_name and scanner_name != source:
            return f"{scanner_name} ({source})"
        return source

    def _proxy_choices(
        self, address: str, current_source: str | None = None
    ) -> dict[str, str]:
        del address
        choices = {AUTO_PROXY_SOURCE: AUTO_PROXY_LABEL}
        by_source: dict[str, str] = {}

        for scanner in async_current_scanners(self.hass):
            if not getattr(scanner, "connectable", False):
                continue
            source = scanner.source
            if source in by_source:
                continue
            by_source[source] = self._proxy_choice_label(
                source, getattr(scanner, "name", None)
            )

        if current_source and current_source not in by_source:
            scanner = async_scanner_by_source(self.hass, current_source)
            by_source[current_source] = (
                f"{self._proxy_choice_label(current_source, getattr(scanner, 'name', None) if scanner else None)}"
                " (saved)"
            )

        for source, label in sorted(by_source.items(), key=lambda item: item[1].lower()):
            choices[source] = label

        return choices

    def _model_schema(
        self,
        *,
        address: str,
        model: str | None = None,
        preferred_proxy_source: str | None = None,
    ) -> vol.Schema:
        proxy_choices = self._proxy_choices(address, preferred_proxy_source)
        return vol.Schema(
            {
                vol.Required(
                    CONF_MODEL,
                    default=model or next(iter(MODEL_NAMES)),
                ): vol.In(MODEL_NAMES),
                vol.Required(
                    CONF_PREFERRED_PROXY_SOURCE,
                    default=preferred_proxy_source or AUTO_PROXY_SOURCE,
                ): vol.In(proxy_choices),
            }
        )

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
        self._preferred_proxy_source = getattr(discovery_info, "source", None)
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
            self._preferred_proxy_source = None
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
        """Select the model and optional preferred proxy."""
        address = self._address
        if address is None:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            model = user_input[CONF_MODEL]
            preferred_proxy_source = user_input[CONF_PREFERRED_PROXY_SOURCE]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            name = self._name or MODEL_NAMES.get(model, model)
            data: dict[str, Any] = {CONF_ADDRESS: address, CONF_MODEL: model}
            if preferred_proxy_source != AUTO_PROXY_SOURCE:
                data[CONF_PREFERRED_PROXY_SOURCE] = preferred_proxy_source
            return self.async_create_entry(title=name, data=data)

        return self.async_show_form(
            step_id="model",
            data_schema=self._model_schema(
                address=address,
                preferred_proxy_source=self._preferred_proxy_source,
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration for model/proxy selection."""
        entry = self._get_reconfigure_entry()
        address = entry.unique_id or entry.data.get(CONF_ADDRESS)
        if address is None:
            return self.async_abort(reason="no_devices_found")

        current_proxy_source = entry.data.get(CONF_PREFERRED_PROXY_SOURCE)
        if user_input is not None:
            updated_data: dict[str, Any] = {
                **entry.data,
                CONF_MODEL: user_input[CONF_MODEL],
            }
            preferred_proxy_source = user_input[CONF_PREFERRED_PROXY_SOURCE]
            if preferred_proxy_source == AUTO_PROXY_SOURCE:
                updated_data.pop(CONF_PREFERRED_PROXY_SOURCE, None)
            else:
                updated_data[CONF_PREFERRED_PROXY_SOURCE] = preferred_proxy_source
            return self.async_update_reload_and_abort(entry, data=updated_data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._model_schema(
                address=address,
                model=entry.data.get(CONF_MODEL),
                preferred_proxy_source=current_proxy_source,
            ),
            description_placeholders={"name": entry.title},
        )
