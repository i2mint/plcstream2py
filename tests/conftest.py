"""Shared test fixtures for ``plcstream2py``.

The package talks to Siemens S7 PLCs through ``python-snap7``, a thin wrapper around
a native ``snap7`` shared library. That is a declared dependency (see ``setup.cfg``),
so the tests use the real library whenever it is installed -- only then can they
notice an upstream API move, which is exactly the class of breakage this suite
exists to catch.

When it is *not* installed (a bare checkout, a machine without the native library),
the fixtures fall back to a minimal in-memory stand-in so that import-level
regressions can still be tested. The stand-in reproduces the API layout of one
release per ``python-snap7`` layout (see ``SNAP7_STUB_MIRRORS_VERSION``) and reports
it as its ``__version__``; ``tests/test_plc_import.py`` cross-checks its shape against
the real library's, so it cannot quietly drift into fiction.

Every fixture leaves ``sys.modules`` exactly as it found it.
"""

import ctypes
import importlib
import importlib.util
import sys
import types
from contextlib import contextmanager
from enum import IntEnum

import pytest

#: The ``python-snap7`` release whose API each stand-in layout reproduces: ``legacy``
#: is the 1.x module layout (``snap7.types``), ``modern`` the 2.x/3.x one
#: (``snap7.type``). Bump these together with the stand-ins.
SNAP7_STUB_MIRRORS_VERSION = {'legacy': '1.4.1', 'modern': '3.1.2'}

#: The layouts ``plcstream2py.snap7_compat`` supports.
SNAP7_LAYOUTS = tuple(SNAP7_STUB_MIRRORS_VERSION)

#: Whether the genuine ``python-snap7`` is importable. Resolved once, at collection
#: time, so that a stand-in installed by a fixture can never be mistaken for it.
REAL_SNAP7_INSTALLED = importlib.util.find_spec('snap7') is not None

#: The module layout of the genuine ``snap7`` (``'legacy'``/``'modern'``), or ``None``
#: when it is not installed. Resolved at collection time, like the flag above.
INSTALLED_SNAP7_LAYOUT = (
    None
    if not REAL_SNAP7_INSTALLED
    else 'modern'
    if importlib.util.find_spec('snap7.type')
    else 'legacy'
)

#: Area and word-length codes, mirroring the values ``snap7.types`` exposes.
#: ``plcstream2py.raw_plc`` branches on the word-length codes to size its read
#: buffers, so these must stay distinct and match the real library.
_S7_CONSTANTS = dict(
    S7AreaPE=0x81,
    S7AreaPA=0x82,
    S7AreaMK=0x83,
    S7AreaDB=0x84,
    S7AreaCT=0x1C,
    S7AreaTM=0x1D,
    S7WLBit=0x01,
    S7WLByte=0x02,
    S7WLChar=0x03,
    S7WLWord=0x04,
    S7WLInt=0x05,
    S7WLDWord=0x06,
    S7WLDInt=0x07,
    S7WLReal=0x08,
)

#: Top-level packages re-imported from scratch inside every fixture, so that each
#: test observes the imports its own body triggers rather than a cached module.
_RELOADED_PACKAGES = ('plcstream2py', 'stream2py')


class _S7DataItem(ctypes.Structure):
    """Stand-in for ``snap7.types.S7DataItem``, laid out like the real structure."""

    _pack_ = 1
    _fields_ = [
        ('Area', ctypes.c_int32),
        ('WordLen', ctypes.c_int32),
        ('Result', ctypes.c_int32),
        ('DBNumber', ctypes.c_int32),
        ('Start', ctypes.c_int32),
        ('Amount', ctypes.c_int32),
        ('pData', ctypes.POINTER(ctypes.c_uint8)),
    ]


class _Snap7Exception(Exception):
    """Stand-in for ``snap7.exceptions.Snap7Exception``."""


class _Client:
    """Stand-in for ``snap7.client.Client``: connects to nothing, reads nothing."""

    def connect(self, ip_address, rack, slot, tcp_port=102):
        return None

    def get_connected(self):
        return False

    def disconnect(self):
        return None

    def destroy(self):
        return None

    def read_multi_vars(self, items):
        return 1, items

    def get_cpu_info(self):
        raise _Snap7Exception('stub client is never connected')

    def get_cpu_state(self):
        raise _Snap7Exception('stub client is never connected')

    def get_pdu_length(self):
        raise _Snap7Exception('stub client is never connected')


class _Area(IntEnum):
    """Stand-in for ``snap7.type.Area`` (2.x+)."""

    PE = 0x81
    PA = 0x82
    MK = 0x83
    DB = 0x84
    CT = 0x1C
    TM = 0x1D


class _WordLen(IntEnum):
    """Stand-in for ``snap7.type.WordLen`` (2.x+)."""

    Bit = 0x01
    Byte = 0x02
    Char = 0x03
    Word = 0x04
    Int = 0x05
    DWord = 0x06
    DInt = 0x07
    Real = 0x08


def _build_snap7_stub(layout='legacy'):
    """Build the stand-in ``snap7`` package as a ``{module name: module}`` mapping.

    ``layout`` is ``'legacy'`` (python-snap7 1.x module names) or ``'modern'``
    (2.x/3.x: ``snap7.type`` and ``snap7.error``, no ``snap7.exceptions``).
    """

    def module(name, **attributes):
        stub_module = types.ModuleType(name)
        stub_module.__dict__.update(attributes)
        return stub_module

    def check_error(code, context='client'):
        if code:
            raise _Snap7Exception(f'stub snap7 error {code} in {context}')

    util = module(
        'snap7.util',
        get_bool=lambda _bytearray, byte_index, bool_index: False,
        get_dword=lambda _bytearray, byte_index: 0,
        get_int=lambda _bytearray, byte_index: 0,
        get_real=lambda _bytearray, byte_index: 0.0,
        get_string=lambda _bytearray, byte_index: '',
    )
    if layout == 'legacy':
        submodules = dict(
            client=module('snap7.client', Client=_Client),
            common=module('snap7.common', check_error=check_error),
            exceptions=module('snap7.exceptions', Snap7Exception=_Snap7Exception),
            types=module('snap7.types', S7DataItem=_S7DataItem, **_S7_CONSTANTS),
            util=util,
        )
    else:
        submodules = dict(
            client=module('snap7.client', Client=_Client),
            error=module('snap7.error', check_error=check_error),
            type=module('snap7.type', S7DataItem=_S7DataItem, Area=_Area, WordLen=_WordLen),
            util=util,
        )
    snap7 = module(
        'snap7', __version__=SNAP7_STUB_MIRRORS_VERSION[layout], **submodules
    )
    return {
        'snap7': snap7,
        **{f'snap7.{name}': mod for name, mod in submodules.items()},
    }


def _submodule_names(top_level_names):
    """The entries of ``sys.modules`` belonging to any of ``top_level_names``."""
    return [
        name
        for name in list(sys.modules)
        if any(
            name == top_level or name.startswith(f'{top_level}.')
            for top_level in top_level_names
        )
    ]


@contextmanager
def _modules_reimported(top_level_names, *, replace_with=None):
    """Force ``top_level_names`` to import afresh inside the block.

    Matching entries are evicted from ``sys.modules`` on the way in and on the way
    out -- so the block's imports really execute, and nothing they leave behind
    outlives the block -- after which ``sys.modules`` is restored as it was found.
    ``replace_with`` is a ``{module name: module}`` mapping installed for the block,
    shadowing whatever is on disk.
    """
    evicted = _submodule_names(top_level_names)
    saved = {name: sys.modules[name] for name in evicted}
    for name in evicted:
        del sys.modules[name]
    sys.modules.update(replace_with or {})
    try:
        yield
    finally:
        for name in _submodule_names(top_level_names):
            del sys.modules[name]
        sys.modules.update(saved)


@contextmanager
def snap7_stub_installed(layout='legacy'):
    """Run the block with the stand-in ``snap7`` importable, then undo every trace."""
    with _modules_reimported(
        _RELOADED_PACKAGES + ('snap7',), replace_with=_build_snap7_stub(layout)
    ):
        yield


@pytest.fixture(params=SNAP7_LAYOUTS)
def stubbed_snap7(request):
    """Make the stand-in ``snap7`` importable, whether or not the real one is here.

    Runs once per layout (``legacy`` and ``modern``); the layout is the fixture's
    value. Use this to test what holds with no native ``snap7`` library at all --
    and to test the stand-in itself.
    """
    with snap7_stub_installed(request.param):
        yield request.param


@contextmanager
def snap7_env(layout):
    """Run the block with a ``snap7`` of the given layout importable.

    Uses the genuine library when the installed one has that layout, the stand-in
    otherwise -- so every layout is exercised on every machine, and against the real
    thing wherever it is installed. Leaves ``sys.modules`` as it found it.
    """
    if INSTALLED_SNAP7_LAYOUT == layout:
        with _modules_reimported(_RELOADED_PACKAGES):
            yield
    else:
        with snap7_stub_installed(layout):
            yield


@pytest.fixture(params=SNAP7_LAYOUTS)
def snap7_layout(request):
    """Run the test once per ``python-snap7`` layout; the value is the layout name."""
    with snap7_env(request.param):
        yield request.param


@pytest.fixture
def importable_snap7():
    """Guarantee ``snap7`` imports: the real library if installed, else the stand-in.

    This is the fixture for tests about ``plcstream2py`` rather than about ``snap7``:
    it exercises the real dependency wherever there is one, and still runs in a bare
    environment.
    """
    if REAL_SNAP7_INSTALLED:
        with _modules_reimported(_RELOADED_PACKAGES):
            yield
    else:
        with snap7_stub_installed():
            yield


@pytest.fixture
def real_snap7():
    """The genuine ``python-snap7``; skips the test when it is not installed."""
    if not REAL_SNAP7_INSTALLED:
        pytest.skip('python-snap7 is not installed in this environment')
    with _modules_reimported(_RELOADED_PACKAGES):
        yield importlib.import_module('snap7')
