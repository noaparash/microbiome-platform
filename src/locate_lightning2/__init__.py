"""LOCATE for Lightning 2 (Python 3.13): the authors' model with only the changes Lightning 2 requires.

Based on LOCATE-model 0.0.3 (Shtossel et al., Microbiome 2024; github.com/oshritshtossel/LOCATE,
MIT licence, see LICENSE.txt). Same functions and arguments as the original package:
``LOCATE_training``, ``LOCATE_predict`` and ``LOCATE_Model``. Every change is marked
``[lightning2]`` in the code and listed in CHANGES.md; the model's logic is unchanged.

This package does not import ``microplatform``, so it can also be tested on its own.
"""

from .LOCATE_model import GeneralModel as LOCATE_Model
from .LOCATE_functions import LOCATE_training, LOCATE_predict

__version__ = "0.1.0"
BASED_ON = "LOCATE-model 0.0.3"

__all__ = ["LOCATE_Model", "LOCATE_training", "LOCATE_predict", "__version__", "BASED_ON"]
