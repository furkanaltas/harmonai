"""pytest kök yapılandırması — proje kökünü sys.path'e ekler ki
testler `from modules...` importlarını çalıştırabilsin."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
