"""Tests for the BLNET sensor component."""
import unittest
from unittest.mock import Mock, patch
from datetime import datetime

from custom_components.blnet.sensor import BLNETComponent
from custom_components.blnet import BLNETDataHandler, BLNETConnector

class TestBLNETComponent(unittest.TestCase):
    """Test the BLNETComponent class."""

    def setUp(self):
        """Set up test variables."""
        self.hass = Mock()
        self.communication = Mock()
        self.communication.data = {}
        self.communication.last_updated = Mock(return_value=datetime.now())

    def test_init_with_numeric_sensor_id(self):
        """Test initialization with numeric sensor_id."""
        sensor = BLNETComponent(
            hass=self.hass,
            sensor_id=1,
            name="test_sensor",
            blnet_id="test_blnet_1",
            friendly_name="Test Sensor",
            communication=self.communication
        )
        self.assertEqual(sensor._identifier, "test_blnet_1")
        self.assertEqual(sensor._friendly_name, "Test Sensor")
        self.assertEqual(sensor._name, "test_sensor")
        self.assertEqual(sensor.name, "test_sensor")

    def test_init_with_string_sensor_id(self):
        """Test initialization with string sensor_id."""
        sensor = BLNETComponent(
            hass=self.hass,
            sensor_id="A1",
            name="test_sensor",
            blnet_id="test_blnet_A1",
            friendly_name="Test Sensor",
            communication=self.communication
        )
        self.assertEqual(sensor._identifier, "test_blnet_A1")
        self.assertEqual(sensor._friendly_name, "Test Sensor")


class TestBLNETDataHandler(unittest.TestCase):
    """Test the BLNETDataHandler class."""

    def setUp(self):
        """Set up test variables."""
        self.hass = Mock()
        self.blnet = Mock()
        self.config = {
            'resource': 'http://example.com',
            'password': 'test',
            'web_port': 80,
            'ta_port': 40000,
            'use_web': True,
            'use_ta': False
        }
        self.node = 1

    def test_init(self):
        """Test initialization of data handler."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        self.assertEqual(handler.blnet, self.blnet)
        self.assertEqual(handler.node, self.node)
        self.assertEqual(handler._hass, self.hass)
        self.assertEqual(handler._config, self.config)
        self.assertEqual(handler.data, {})
        self.assertIsNone(handler._last_updated)

    def test_last_updated(self):
        """Test last_updated method."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        self.assertIsNone(handler.last_updated())
        handler._last_updated = datetime.now()
        self.assertIsNotNone(handler.last_updated())

    def test_turn_on_off(self):
        """Test turn_on and turn_off methods."""
        handler = BLNETDataHandler(self.blnet, self.node, self.hass, self.config)
        
        # Test turn_on
        handler.turn_on(1)
        self.blnet.turn_on.assert_called_once_with(1, self.node)
        
        # Test turn_off
        handler.turn_off(1)
        self.blnet.turn_off.assert_called_once_with(1, self.node)
        
        # Test turn_auto
        handler.turn_auto(1)
        self.blnet.turn_auto.assert_called_once_with(1, self.node)


class TestBLNETConnector(unittest.TestCase):
    """Test the BLNETConnector class."""

    def test_init(self):
        """Test initialization of connector."""
        connector = BLNETConnector(
            resource='http://example.com',
            password='test',
            web_port=80,
            ta_port=40000,
            use_web=True,
            use_ta=False
        )
        self.assertEqual(connector.resource, 'http://example.com')
        self.assertEqual(connector.password, 'test')
        self.assertEqual(connector.web_port, 80)
        self.assertEqual(connector.ta_port, 40000)
        self.assertTrue(connector.use_web)
        self.assertFalse(connector.use_ta)

    @patch('pyblnet.BLNET')
    def test_connect(self, mock_blnet):
        """Test connect method."""
        connector = BLNETConnector(
            resource='http://example.com',
            password='test'
        )
        connector.connect()
        mock_blnet.assert_called_once_with(
            'http://example.com',
            password='test',
            web_port=80,
            ta_port=40000,
            use_web=True,
            use_ta=False
        )


class TestBLNETDataHandlerUpdate(unittest.TestCase):
    """Test update() on data shaped like pyblnet's BLNET.fetch()."""

    # Values read only via the direct connection (use_web: false) have no name
    TA_ONLY_DATA = {
        'analog': {
            1: {'value': 21.3, 'type': 'temperature', 'unit_of_measurement': '°C'},
            2: {'value': 300.0, 'type': 'volume_flow', 'unit_of_measurement': 'l/h'},
            3: {'value': 512.0, 'type': 'radiation', 'unit_of_measurement': 'W/m²'},
        },
        'digital': {1: {'value': '1'}, 2: {'value': '0'}},
        'speed': {1: {'value': 30, 'unit_of_measurement': None}},
        'energy': {1: {'value': 12.3, 'unit_of_measurement': 'kWh'}},
        'power': {1: {'value': 1.2, 'unit_of_measurement': 'kW'}},
    }

    def _update(self, data, use_web):
        blnet = Mock()
        blnet.fetch.return_value = data
        handler = BLNETDataHandler(blnet, None, Mock(), {'use_web': use_web})
        with patch('custom_components.blnet.load_platform') as load_platform:
            handler.update()
            # values that are already set up are not added again
            handler.update()
        return handler, load_platform

    def test_update_direct_only(self):
        """Every value gets an entity, even without a name."""
        handler, load_platform = self._update(self.TA_ONLY_DATA, use_web=False)

        self.assertEqual(load_platform.call_count, 8)
        added = {call.args[3]['blnet_id']: call for call in load_platform.call_args_list}
        self.assertEqual(set(added), set(handler.data))
        # digital values are read-only sensors without the web interface
        self.assertEqual(added['blnet digital 1'].args[1], 'sensor')
        self.assertEqual(added['blnet speed 1'].args[3]['name'], 'speed 1')

        self.assertEqual(handler.data['blnet analog 1'], {
            'value': 21.3,
            'unit_of_measurement': '°C',
            'friendly_name': 'analog 1',
            'icon': 'mdi:thermometer',
        })
        self.assertEqual(handler.data['blnet analog 2']['icon'], 'mdi:water-pump')
        self.assertEqual(handler.data['blnet analog 3']['icon'], 'mdi:white-balance-sunny')
        self.assertEqual(handler.data['blnet energy 1']['unit_of_measurement'], 'kWh')
        self.assertEqual(handler.data['blnet digital 2']['value'], '0')

    def test_update_web_same_names(self):
        """Values sharing a name in the web interface each get an entity."""
        data = {
            'analog': {
                1: {'id': '1', 'name': 'T.Speicher', 'value': '55.0',
                    'unit_of_measurement': '°C', 'type': 'temperature'},
                2: {'id': '2', 'name': 'T.Speicher', 'value': '40.0',
                    'unit_of_measurement': '°C', 'type': 'temperature'},
                3: {'id': '3', 'name': 'Schalter', 'value': '1',
                    'unit_of_measurement': None, 'type': 'digital'},
            },
            'digital': {1: {'id': '1', 'name': 'Pumpe', 'mode': 'AUTO', 'value': 'EIN'}},
            'speed': {}, 'energy': {}, 'power': {},
        }
        handler, load_platform = self._update(data, use_web=True)

        self.assertEqual(load_platform.call_count, 4)
        self.assertEqual(handler.data['blnet analog 2']['friendly_name'], 'T.Speicher')
        self.assertEqual(handler.data['blnet analog 3']['icon'], 'mdi:toggle-switch')
        switch = [c for c in load_platform.call_args_list if c.args[3]['domain'] == 'digital']
        self.assertEqual(switch[0].args[1], 'switch')
        self.assertEqual(handler.data['blnet digital 1']['mode'], 'AUTO')


if __name__ == '__main__':
    unittest.main() 
