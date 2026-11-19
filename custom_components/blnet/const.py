"""Constants of the BLNET integration."""

DOMAIN = "blnet"

CONF_WEB_PORT = "web_port"
CONF_TA_PORT = "ta_port"
CONF_USE_WEB = "use_web"
CONF_USE_TA = "use_ta"
CONF_NODE = "can_node"

DEFAULT_WEB_PORT = 80
DEFAULT_TA_PORT = 40000
DEFAULT_SCAN_INTERVAL = 360

# Domains of the values pyblnet fetches that become sensors
SENSOR_DOMAINS = ("analog", "speed", "power", "energy")
# Digital outputs, switches with the web interface and sensors without it
DIGITAL = "digital"
