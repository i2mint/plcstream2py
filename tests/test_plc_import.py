"""Import-level regression tests for :mod:`plcstream2py.plc`.

``plcstream2py.plc`` used to pull ``PlcRawRead``, ``PlcDataItem`` and ``get_byte``
from ``stream2py.sources.raw_plc``. stream2py deleted that module when it dropped its
bundled sources, and the code was relocated into this package as
:mod:`plcstream2py.raw_plc` -- but the import statement was never updated, so
``plcstream2py.plc`` raised ``ModuleNotFoundError`` on any current stream2py.

That was one instance of a general failure mode: a module the package imports by path
goes away upstream, and nothing notices until a user tries to import. The tests here
cover both halves of it -- that ``plcstream2py.plc`` imports, and that every
``snap7`` attribute the package hard-codes still exists in the library it is pinned
to. When ``python-snap7`` is installed they run against it; see ``tests/conftest.py``
for the stand-in used when it is not.
"""

import importlib
import sys

import pytest

#: The names :mod:`plcstream2py.plc` needs from the relocated raw-PLC module.
RELOCATED_NAMES = ('PlcRawRead', 'PlcDataItem', 'get_byte')

#: The module that used to provide them, and must never be reached again.
ABANDONED_SOURCE_MODULE = 'stream2py.sources.raw_plc'

#: Every ``snap7`` attribute ``plcstream2py`` reaches for by path. A ``python-snap7``
#: release that moves or renames any of these breaks the package on import, so this
#: is the contract both the real library and the test stand-in must satisfy.
SNAP7_ATTRIBUTES_USED = {
    'snap7.client': ('Client',),
    'snap7.common': ('check_error',),
    'snap7.exceptions': ('Snap7Exception',),
    'snap7.types': (
        'S7DataItem',
        'S7AreaDB',
        'S7WLBit',
        'S7WLByte',
        'S7WLWord',
        'S7WLDWord',
        'S7WLReal',
    ),
    'snap7.util': ('get_bool', 'get_dword', 'get_int', 'get_real', 'get_string'),
}


def _missing_snap7_attributes():
    """The ``SNAP7_ATTRIBUTES_USED`` entries the importable ``snap7`` does not have."""
    return [
        f'{module_name}.{attribute}'
        for module_name, attributes in SNAP7_ATTRIBUTES_USED.items()
        for attribute in attributes
        if not hasattr(importlib.import_module(module_name), attribute)
    ]


def test_plc_module_is_importable(importable_snap7):
    """``plcstream2py.plc`` imports, given ``snap7`` and the declared dependencies."""
    plc = importlib.import_module('plcstream2py.plc')
    assert hasattr(plc, 'PlcReader')


def test_raw_plc_names_come_from_this_package(importable_snap7):
    """The raw-PLC names come from this package, not from a stream2py submodule."""
    importlib.import_module('plcstream2py.plc')

    # Asserted on what the import pulled in, not on how plc.py spells the import,
    # so that a rewrite of the import statement does not turn this red for nothing.
    assert 'plcstream2py.raw_plc' in sys.modules
    assert ABANDONED_SOURCE_MODULE not in sys.modules

    raw_plc = sys.modules['plcstream2py.raw_plc']
    assert [name for name in RELOCATED_NAMES if not hasattr(raw_plc, name)] == []


@pytest.mark.parametrize('snap7_source', ('real_snap7', 'stubbed_snap7'))
def test_snap7_provides_the_attributes_the_package_uses(snap7_source, request):
    """Both the installed ``python-snap7`` and the test stand-in honour the contract.

    Against the real library this catches an upstream move of any attribute
    ``plcstream2py`` hard-codes; against the stand-in it stops that stand-in from
    drifting away from the shape it claims to have.
    """
    request.getfixturevalue(snap7_source)
    assert _missing_snap7_attributes() == []
