from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Convention unique pour tout le paquet : image BGR (ordre natif d'OpenCV), HxWx3, uint8.
Image = NDArray[np.uint8]
