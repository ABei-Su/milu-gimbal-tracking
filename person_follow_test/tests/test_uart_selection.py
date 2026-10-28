import unittest
from pathlib import Path

from milu.settings import Settings, load_settings


class UARTSelectionTests(unittest.TestCase):
    def test_defaults_and_shipped_config_select_uart2(self):
        config = Path(__file__).resolve().parents[1] / "config.json"
        for cfg in (Settings(), load_settings(config)):
            self.assertEqual(
                (cfg.uart_device, cfg.tx_pin, cfg.rx_pin, cfg.tx_function, cfg.rx_function),
                ("/dev/ttyS2", "B0", "B1", "UART2_TX", "UART2_RX"),
            )
