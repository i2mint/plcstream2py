"""Import-level regression tests for :mod:`plcstream2py.plc`.

``plcstream2py.plc`` used to pull ``PlcRawRead``, ``PlcDataItem`` and
``get_byte`` from ``stream2py.sources.raw_plc``. stream2py deleted that module
when it dropped its bundled sources, and the code was relocated into this
package as :mod:`plcstream2py.raw_plc` -- but the import statement was never
updated, so ``plcstream2py.plc`` raised ``ModuleNotFoundError`` on any current
stream2py. These tests import the module (against a stubbed ``snap7``) so the
stale import cannot come back unnoticed.
"""

import importlib

import pytest

#: The names ``plcstream2py.plc`` needs from the relocated raw-PLC module.
RELOCATED_NAMES = ('PlcRawRead', 'PlcDataItem', 'get_byte')


def test_plc_module_is_importable(stubbed_snap7):
    """``plcstream2py.plc`` imports cleanly with only its declared dependencies."""
    plc = importlib.import_module('plcstream2py.plc')
    assert hasattr(plc, 'PlcReader')


@pytest.mark.parametrize('name', RELOCATED_NAMES)
def test_plc_uses_the_packages_own_raw_plc(stubbed_snap7, name):
    """The raw-PLC names come from this package, not from a stream2py submodule."""
    plc = importlib.import_module('plcstream2py.plc')
    raw_plc = importlib.import_module('plcstream2py.raw_plc')
    assert getattr(plc, name) is getattr(raw_plc, name)
