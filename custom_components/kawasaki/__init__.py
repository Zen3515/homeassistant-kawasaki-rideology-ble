"""The Kawasaki BLE integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .config import async_load_model_config
from .const import CONF_MODEL, CONF_PREFERRED_PROXY_SOURCE
from .coordinator import KawasakiCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type KawasakiConfigEntry = ConfigEntry[KawasakiCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: KawasakiConfigEntry) -> bool:
    """Set up Kawasaki from a config entry."""
    address = entry.unique_id or entry.data.get(CONF_ADDRESS)
    model = entry.data.get(CONF_MODEL)
    preferred_proxy_source = entry.data.get(CONF_PREFERRED_PROXY_SOURCE)
    _LOGGER.debug(
        "Setting up config entry %s for address %s, model %s, preferred_proxy_source=%s",
        entry.entry_id,
        address,
        model,
        preferred_proxy_source,
    )
    if not address or not model:
        _LOGGER.error(
            "Missing required config values for entry %s: address=%s model=%s",
            entry.entry_id,
            address,
            model,
        )
        return False

    config = await async_load_model_config(hass, model)
    coordinator = KawasakiCoordinator(
        hass,
        address=address,
        model=model,
        config=config,
        preferred_proxy_source=preferred_proxy_source,
    )
    await coordinator.async_start()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Finished setup for entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KawasakiConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data:
        await entry.runtime_data.async_stop()
    _LOGGER.debug("Finished unload for entry %s with unload_ok=%s", entry.entry_id, unload_ok)
    return unload_ok
