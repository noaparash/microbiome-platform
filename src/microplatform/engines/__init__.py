"""Engines: one adapter per tool, all implementing ``engines.base.Engine``.

To add a tool, write its engine in a new file and register it here.
``tests/test_contract.py`` then checks that it follows the shared data contract.
"""

from microplatform.engines.base import Engine, EngineOption, EngineResult
from microplatform.engines.gimic import GimicEngine
from microplatform.engines.imic import ImicEngine
from microplatform.engines.mimic import MimicEngine
from microplatform.engines.mipmlp import MipmlpEngine

# goal id → engine
ENGINES: dict[str, Engine] = {
    engine.goal: engine for engine in (MipmlpEngine(), MimicEngine(), GimicEngine(), ImicEngine())
}

__all__ = ["ENGINES", "Engine", "EngineOption", "EngineResult"]
