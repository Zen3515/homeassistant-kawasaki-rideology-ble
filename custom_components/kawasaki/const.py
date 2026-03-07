"""Constants for the Kawasaki integration."""

from __future__ import annotations

DOMAIN = "kawasaki"
CONF_MODEL = "model"
CONF_PREFERRED_PROXY_SOURCE = "preferred_proxy_source"

MODEL_Z500 = "z500"
MODEL_NAMES = {
    MODEL_Z500: "Z500 (ER500F)",
}
MODEL_CONFIGS = {
    MODEL_Z500: "z500_er500f_config.json",
}

NAME_PREFIXES = ("Kawasaki-", "Kawasaki")
