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

#: Every ``snap7`` attribute ``plcstream2py.snap7_compat`` reaches for by path, per
#: module layout. A ``python-snap7`` release that moves or renames any of these breaks
#: the package on import, so this is the contract both the real library and the test
#: stand-ins must satisfy.
_UTIL_NAMES = ('get_bool', 'get_dword', 'get_int', 'get_real', 'get_string')
SNAP7_ATTRIBUTES_USED = {
    'legacy': {
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
        'snap7.util': _UTIL_NAMES,
    },
    'modern': {
        'snap7.client': ('Client',),
        'snap7.error': ('check_error',),
        'snap7.type': ('S7DataItem', 'Area', 'WordLen'),
        'snap7.util': _UTIL_NAMES,
    },
}

#: The ``snap7.client.Client`` methods :class:`plcstream2py.raw_plc.PlcRawRead` calls.
SNAP7_CLIENT_METHODS_USED = (
    'connect',
    'get_connected',
    'disconnect',
    'destroy',
    'get_cpu_info',
    'get_cpu_state',
    'get_pdu_length',
    'read_multi_vars',
)


def _installed_layout():
    """The layout of the ``snap7`` currently importable."""
    try:
        importlib.import_module('snap7.type')
    except ModuleNotFoundError:
        return 'legacy'
    return 'modern'


def _missing_snap7_attributes():
    """The ``SNAP7_ATTRIBUTES_USED`` entries the importable ``snap7`` does not have."""
    return [
        f'{module_name}.{attribute}'
        for module_name, attributes in SNAP7_ATTRIBUTES_USED[_installed_layout()].items()
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


def test_real_snap7_provides_the_attributes_the_package_uses(real_snap7):
    """The installed ``python-snap7`` honours the contract.

    This catches an upstream move of any attribute ``plcstream2py`` hard-codes.
    """
    assert _missing_snap7_attributes() == []


def test_snap7_stand_ins_provide_the_attributes_the_package_uses(stubbed_snap7):
    """Each test stand-in honours the contract, so it cannot drift into fiction."""
    assert _installed_layout() == stubbed_snap7
    assert _missing_snap7_attributes() == []


def test_real_snap7_client_has_the_methods_the_package_calls(real_snap7):
    """The installed ``snap7.client.Client`` still has every method ``PlcRawRead`` calls."""
    client_class = real_snap7.client.Client
    assert [m for m in SNAP7_CLIENT_METHODS_USED if not hasattr(client_class, m)] == []


def test_compat_resolves_the_layout_of_the_snap7_it_finds(snap7_layout):
    """``snap7_compat`` picks the layout that matches the installed ``snap7``."""
    compat = importlib.import_module('plcstream2py.snap7_compat')
    assert compat.SNAP7_LAYOUT == snap7_layout
    assert compat.S7AreaDB == 0x84
    assert (compat.S7WLBit, compat.S7WLByte) == (0x01, 0x02)
    assert compat.WORD_LEN_BYTES[compat.S7WLDWord] == 4
