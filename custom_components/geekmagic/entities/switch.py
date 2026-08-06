"""Switch entities for GeekMagic integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import (
    CONF_DEVICE_SLIDESHOW,
    CONF_SCREEN_CYCLE_INTERVAL,
    DEFAULT_DEVICE_SLIDESHOW,
    DOMAIN,
)
from .base import GeekMagicEntity

if TYPE_CHECKING:
    from ..coordinator import GeekMagicCoordinator

_LOGGER = logging.getLogger(__name__)

# Default cycle interval when turning on (if no previous value stored)
DEFAULT_CYCLE_ON_INTERVAL = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GeekMagic switch entities."""
    coordinator: GeekMagicCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        GeekMagicActiveSwitch(coordinator),
        GeekMagicViewCyclingSwitch(coordinator),
        GeekMagicDeviceSlideshowSwitch(coordinator),
    ]

    async_add_entities(entities)


class GeekMagicActiveSwitch(GeekMagicEntity, SwitchEntity):
    """Switch to pause/resume the render and upload cycle.

    When off, all rendering and device uploads are skipped and the screen is
    dimmed to zero. Intended for presence-based automations so the display
    does not refresh (or stay lit) when no one is in the room.
    """

    _attr_name = "Active"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator: GeekMagicCoordinator) -> None:
        """Initialize active switch."""
        super().__init__(coordinator, "active")

    @property
    def is_on(self) -> bool:
        """Return True when the display is active (not paused)."""
        return self.coordinator.is_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume the display."""
        await self.coordinator.async_set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause the display and dim the screen."""
        await self.coordinator.async_set_active(False)


class GeekMagicViewCyclingSwitch(GeekMagicEntity, SwitchEntity):
    """Switch to enable/disable automatic view cycling.

    When enabled, the display automatically cycles through configured views.
    The cycle interval can be adjusted via the View Cycle Interval number entity.
    """

    _attr_name = "View Cycling"
    _attr_icon = "mdi:view-carousel"

    def __init__(self, coordinator: GeekMagicCoordinator) -> None:
        """Initialize view cycling switch."""
        super().__init__(coordinator, "view_cycling")
        # Store the last non-zero interval so we can restore it when turning on
        self._last_interval: int = DEFAULT_CYCLE_ON_INTERVAL

    @property
    def is_on(self) -> bool:
        """Return True if view cycling is enabled."""
        interval = self.coordinator.options.get(CONF_SCREEN_CYCLE_INTERVAL, 0)
        return interval > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on view cycling."""
        # Get current interval - if already > 0, keep it; otherwise use last or default
        current_interval = self.coordinator.options.get(CONF_SCREEN_CYCLE_INTERVAL, 0)
        if current_interval > 0:
            # Already on, nothing to do
            return

        # Use the last known interval, or default
        new_interval = self._last_interval

        new_options = {
            **self.coordinator.entry.options,
            CONF_SCREEN_CYCLE_INTERVAL: new_interval,
        }
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options=new_options)
        _LOGGER.debug("View cycling enabled with interval %ds", new_interval)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off view cycling."""
        current_interval = self.coordinator.options.get(CONF_SCREEN_CYCLE_INTERVAL, 0)
        if current_interval == 0:
            # Already off, nothing to do
            return

        # Store the current interval so we can restore it later
        self._last_interval = current_interval

        new_options = {
            **self.coordinator.entry.options,
            CONF_SCREEN_CYCLE_INTERVAL: 0,
        }
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options=new_options)
        _LOGGER.debug("View cycling disabled (was %ds)", current_interval)


class GeekMagicDeviceSlideshowSwitch(GeekMagicEntity, SwitchEntity):
    """Switch to hand view cycling over to the device.

    Off (default), the integration cycles: it re-renders and re-uploads one
    file on every refresh, so the refresh interval doubles as the screen-change
    interval and a fast rotation means constant traffic and flash writes.

    On, every view is uploaded as its own file and the firmware's own slideshow
    advances between them. Screen changes then cost nothing, the rotation speed
    is whatever the device is set to, and the refresh interval only governs how
    fresh the data on each image is.
    """

    _attr_name = "Device Slideshow"
    _attr_icon = "mdi:image-multiple"

    def __init__(self, coordinator: GeekMagicCoordinator) -> None:
        """Initialize device slideshow switch."""
        super().__init__(coordinator, "device_slideshow")

    @property
    def available(self) -> bool:
        """Only firmwares with a browsable image album can do this."""
        return super().available and self.coordinator.device.profile.display_mechanism in (
            "direct_image",
            "picture_album",
        )

    @property
    def is_on(self) -> bool:
        """Return True if the device drives the slideshow."""
        return bool(self.coordinator.options.get(CONF_DEVICE_SLIDESHOW, DEFAULT_DEVICE_SLIDESHOW))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Hand cycling over to the device."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Take cycling back into the integration."""
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        if self.is_on == enabled:
            return
        new_options = {**self.coordinator.entry.options, CONF_DEVICE_SLIDESHOW: enabled}
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options=new_options)
        _LOGGER.debug("Device slideshow %s", "enabled" if enabled else "disabled")
