"""Shared test fixtures for ``plcstream2py``.

The package talks to Siemens S7 PLCs through ``python-snap7``, which is a thin
wrapper around a native ``snap7`` shared library. That dependency needs hardware
drivers and is not installed in a bare test environment, so the helpers here put
a minimal in-memory stand-in into ``sys.modules``. This lets import-level
regressions (stale imports, moved modules) be tested without a PLC or the native
library, while leaving ``sys.modules`` exactly as it was found.
"""

import ctypes
import sys
import types
from contextlib import contextmanager

import pytest

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


class _S7DataItem(ctypes.Structure):
    """Stand-in for ``snap7.types.S7DataItem``, with the fields the package uses."""

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


def _build_snap7_stub():
    """Build the fake ``snap7`` package as a ``{module name: module}`` mapping."""

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
        get_byte=lambda _bytearray, byte_index: 0,
        get_int=lambda _bytearray, byte_index: 0,
        get_real=lambda _bytearray, byte_index: 0.0,
        get_dword=lambda _bytearray, byte_index: 0,
        get_string=lambda _bytearray, byte_index: '',
    )
    snap7 = module(
        'snap7',
        client=module('snap7.client', Client=_Client),
        common=module('snap7.common', check_error=check_error),
        exceptions=module('snap7.exceptions', Snap7Exception=_Snap7Exception),
        types=module('snap7.types', S7DataItem=_S7DataItem, **_S7_CONSTANTS),
        util=util,
    )
    return {
        'snap7': snap7,
        'snap7.client': snap7.client,
        'snap7.common': snap7.common,
        'snap7.exceptions': snap7.exceptions,
        'snap7.types': snap7.types,
        'snap7.util': snap7.util,
    }


@contextmanager
def snap7_stub_installed():
    """Run the block with a fake ``snap7`` importable, then undo every trace of it.

    ``plcstream2py`` submodules are evicted on the way in and on the way out so
    that they are imported fresh against the stub, and so that no module left in
    ``sys.modules`` afterwards holds a reference to it.
    """
    stub = _build_snap7_stub()

    def affected_module_names():
        return [
            name
            for name in list(sys.modules)
            if name in stub
            or name == 'plcstream2py'
            or name.startswith('plcstream2py.')
        ]

    saved = {name: sys.modules[name] for name in affected_module_names()}
    for name in affected_module_names():
        del sys.modules[name]
    sys.modules.update(stub)
    try:
        yield
    finally:
        for name in affected_module_names():
            del sys.modules[name]
        sys.modules.update(saved)


@pytest.fixture
def stubbed_snap7():
    """Make a minimal fake ``snap7`` importable for the duration of one test."""
    with snap7_stub_installed():
        yield
