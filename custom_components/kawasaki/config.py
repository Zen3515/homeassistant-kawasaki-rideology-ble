"""Load per-model BLE configs."""

from __future__ import annotations

from importlib import resources
import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import MODEL_CONFIGS

_LOGGER = logging.getLogger(__name__)


def load_model_config(model: str) -> dict[str, Any]:
    """Load the BLE config for the selected model."""
    config_name = MODEL_CONFIGS.get(model)
    if not config_name:
        raise ValueError(f"Unsupported model: {model}")

    config_path = resources.files(__package__).joinpath("configs", config_name)
    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    model_config = data.get("ble5_telemetry", data)
    for key in (
        "startup_frames",
        "debug_frames",
        "log_1b",
        "control_write_with_response",
        "force_start_notify",
        "force_rebond_before_startup",
        "startup_delay_s",
        "startup_inter_frame_delay_s",
        "startup_time_sync",
        "phone_model",
        "client_model",
        "pair_before_startup",
        "require_startup_responses",
        "startup_frame_profiles",
        "startup_wait_frames",
        "startup_wait_timeout_s",
        "startup_wait_poll_s",
        "startup_retries",
        "startup_retry_delay_s",
        "max_pending_frames",
        "log_all_frames",
        "startup_flip_write_mode_on_no_frames",
        "startup_flip_frame_profile_on_no_frames",
        "startup_pair_on_no_frames",
        "mc_info_probe_on_stale",
        "mc_info_stale_after_s",
        "mc_info_probe_interval_s",
        "info_config_flags",
        "info_config_hex",
    ):
        if key in data and key not in model_config:
            model_config[key] = data[key]
    _LOGGER.debug(
        "Loaded model config for %s from %s with keys: %s",
        model,
        config_name,
        sorted(model_config.keys()),
    )
    _LOGGER.debug(
        (
            "Effective startup config for %s: control_write_with_response=%s "
            "require_startup_responses=%s startup_frames=%s "
            "startup_frame_profiles=%s pair_before_startup=%s"
        ),
        model,
        model_config.get("control_write_with_response"),
        model_config.get("require_startup_responses"),
        model_config.get("startup_frames"),
        model_config.get("startup_frame_profiles"),
        model_config.get("pair_before_startup"),
    )
    return model_config


async def async_load_model_config(
    hass: HomeAssistant, model: str
) -> dict[str, Any]:
    """Load the BLE config in the executor to avoid blocking the event loop."""
    _LOGGER.debug("Loading model config for %s in executor", model)
    return await hass.async_add_executor_job(load_model_config, model)
