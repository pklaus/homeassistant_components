"""
Support for Brother QL Label Printers
"""
import logging
from datetime import timedelta

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    CONF_HOST, CONF_NAME, STATE_UNKNOWN)

REQUIREMENTS = ['pysnmp==4.3.9', 'brother_ql==0.7.5']

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = 'localhost'
DEFAULT_NAME = 'Brother QL'
DEFAULT_PORT = '161'

SCAN_INTERVAL = timedelta(seconds=2)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})

BASEOID = '1.3.6.1.4.1.2435.3.3.9.1.6.1.0'

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the SNMP sensor."""
    from pysnmp.hlapi import (
        getCmd, CommunityData, SnmpEngine, UdpTransportTarget, ContextData,
        ObjectType, ObjectIdentity)

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)

    errindication, _, _, _ = next(
        getCmd(SnmpEngine(),
               CommunityData('public', mpModel=0),
               UdpTransportTarget((host, 161)),
               ContextData(),
               ObjectType(ObjectIdentity(BASEOID))))

    if errindication:
        _LOGGER.error("Please check the details in the configuration file")
        return False
    else:
        data = BrotherQLData(host)
        add_devices([BrotherQLSensor(data, name)], True)


class BrotherQLSensor(Entity):
    """Representation of a Brother QL sensor."""

    def __init__(self, data, name):
        """Initialize the sensor."""
        self.data = data
        self._name = name
        self._state = None
        self._unit_of_measurement = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        attrs = {}
        attrs['media_type'] =   self.data.media_type
        attrs['media_width'] =  self.data.media_width
        attrs['media_length'] = self.data.media_length
        attrs['phase'] =        self.data.phase
        attrs['errors'] =       self.data.errors
        return attrs

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit the state value is expressed in."""
        return self._unit_of_measurement

    def update(self):
        """Get the latest data and updates the states."""
        self.data.update()
        self._state = self.data.state


class BrotherQLData(object):
    """Get the latest data and update the states."""

    def __init__(self, host):
        """Initialize the data object."""
        self._host = host
        self._port = 161
        self._community = 'public'
        self._baseoid = BASEOID

        self.state = STATE_UNKNOWN
        self.media_type = STATE_UNKNOWN
        self.media_width = STATE_UNKNOWN
        self.media_length = STATE_UNKNOWN
        self.phase = STATE_UNKNOWN
        self.errors = STATE_UNKNOWN

    def update(self):
        """Get the latest data from the remote SNMP capable host."""
        from pysnmp.hlapi import (
            getCmd, CommunityData, SnmpEngine, UdpTransportTarget, ContextData,
            ObjectType, ObjectIdentity)
        from brother_ql.reader import interpret_response
        errindication, errstatus, errindex, restable = next(
            getCmd(SnmpEngine(),
                   CommunityData(self._community, mpModel=0),
                   UdpTransportTarget((self._host, self._port)),
                   ContextData(),
                   ObjectType(ObjectIdentity(self._baseoid)))
            )

        if errindication:
            _LOGGER.error("SNMP error: %s", errindication)
        elif errstatus:
            _LOGGER.error("SNMP error: %s at %s", errstatus.prettyPrint(),
                          errindex and restable[-1][int(errindex) - 1] or '?')
        else:
            assert len(restable) == 1
            status = interpret_response(bytes(restable[0][1]))
            self.media_type = status['media_type']
            self.media_width = '{} mm'.format(status['media_width'])
            self.media_length = status['media_length'] or 'endless'
            self.phase = status['phase_type']
            self.errors = ', '.join(status['errors']) or '-none-'
            if status['errors']:
                self.state = 'error'
            elif 'waiting' in status['phase_type'].lower():
                self.state = 'idle'
            elif 'printing' in status['phase_type'].lower():
                self.state = 'printing'
            else:
                self.state = STATE_UNKNOWN

