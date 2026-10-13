"""Tests for reading items through :mod:`plcstream2py.raw_plc`, on every snap7 flavour.

No PLC exists in CI, so the client is a fake injected into ``PlcRawRead``. What these
tests pin down is the part that differs between ``python-snap7`` releases:

- ``legacy`` (1.x) and ``modern-native`` (2.x): one ``read_multi_vars`` call, in which
  the native library honours each item's ``WordLen`` (a bit item addresses one bit);
- ``modern-pure-python`` (3.x): ``read_multi_vars`` ignores ``WordLen`` and a typed
  ``read_area`` mis-parses bit/real answers, so plain bytes are read per item and the
  bits are extracted here.

Every flavour must produce the same values for the same memory.
:class:`TestAgainstSnap7Server` goes further when ``python-snap7`` 3.x is installed: it
talks to the pure-Python S7 server that ships with it, over loopback.
"""

import importlib
import importlib.util
import socket
import struct

import pytest

from conftest import INSTALLED_SNAP7_LAYOUT, snap7_env

#: What the fake PLC holds in DB 1: byte 0 = 0b10 (bit 0 clear, bit 1 set), a byte at
#: 3 and 4, a big-endian REAL 3.5 at 8, a big-endian WORD 0x1234 at 12, and bytes 14-15
#: for a multi-bit read that crosses a byte boundary (bits 118, 119, 120 are 1, 1, 1).
MEMORY = {1: bytearray(b'\x02\x00\x00\x4d\xc8\x00\x00\x00' + struct.pack('>f', 3.5)
                       + b'\x12\x34\xc0\x01')}

#: ``(key, expected value)`` for the items built by :func:`_data_items`.
EXPECTED = {'led': True, 'motor': False, 'speed': 77, 'real': 3.5, 'word': 0x1234}

_WIRE_BYTES = {1: 1, 2: 1, 4: 2, 6: 4, 8: 4}  # word length code -> bytes per element


def _get_bool(buffer, byte_index, bool_index):
    """Same contract as ``snap7.util.get_bool``; local so the stand-in util is moot."""
    return bool(buffer[byte_index] >> bool_index & 1)


def _get_real(buffer, byte_index):
    return struct.unpack('>f', bytes(buffer[byte_index : byte_index + 4]))[0]


def _get_word(buffer, byte_index):
    return int.from_bytes(bytes(buffer[byte_index : byte_index + 2]), 'big')


class _NativeClient:
    """Fake of the 1.x/2.x client: ``read_multi_vars`` honours each item's word length."""

    def __init__(self, memory, *, status=0):
        self.memory, self.status, self.calls = memory, status, []

    def read_multi_vars(self, items):
        self.calls.append([(i.WordLen, i.DBNumber, i.Start, i.Amount) for i in items])
        for item in items:
            memory = self.memory[item.DBNumber]
            if item.WordLen == 0x01:  # a bit item: Amount bits from bit offset Start
                for i in range(item.Amount):
                    byte, bit = divmod(item.Start + i, 8)
                    item.pData[i] = memory[byte] >> bit & 1
            else:
                size = _WIRE_BYTES[item.WordLen] * item.Amount
                for i, value in enumerate(memory[item.Start : item.Start + size]):
                    item.pData[i] = value
            item.Result = 0
        return self.status, items


class _PurePythonClient:
    """Fake of the 3.x client, as far as it matters here.

    ``read_multi_vars`` and a typed ``read_area`` are both traps: the first is blind
    to word lengths, the second returns no data for bits and reals.
    """

    def __init__(self, memory):
        self.memory, self.calls = memory, []

    def read_multi_vars(self, items):
        raise AssertionError('the word-length-blind multi-variable read must not be used')

    def read_area(self, area, db_number, start, size, word_len=None):
        assert word_len is None, 'a typed read_area returns nothing for bits and reals'
        self.calls.append((int(area), db_number, start, size))
        return bytearray(self.memory[db_number][start : start + size])


@pytest.fixture(params=['legacy', 'modern-native', 'modern-pure-python'])
def flavour(request, monkeypatch):
    """``(name, client)`` for each snap7 flavour, with ``snap7_compat`` set up for it."""
    layout, _, kind = request.param.partition('-')
    with snap7_env(layout):
        compat = importlib.import_module('plcstream2py.snap7_compat')
        pure_python = kind == 'pure-python'
        monkeypatch.setattr(compat, '_is_pure_python_client', lambda: pure_python)
        yield request.param, (_PurePythonClient if pure_python else _NativeClient)(MEMORY)


def _raw_reader(client):
    from plcstream2py.raw_plc import PlcRawRead

    reader = PlcRawRead('127.0.0.1', rack=0, slot=0)
    reader._plc = client
    return reader


def _data_items():
    from plcstream2py.raw_plc import PlcDataItem, get_byte
    from plcstream2py.snap7_compat import (
        S7AreaDB, S7WLBit, S7WLByte, S7WLReal, S7WLWord,
    )

    def item(word_len, start, key, convert, convert_args, amount=1):
        return PlcDataItem(
            S7AreaDB, word_len, 1, start, amount, key, convert, convert_args
        )

    return [
        item(S7WLBit, 0 * 8 + 1, 'led', _get_bool, (0, 0)),
        item(S7WLBit, 0 * 8 + 0, 'motor', _get_bool, (0, 0)),
        item(S7WLByte, 3, 'speed', get_byte, (0,)),
        item(S7WLReal, 8, 'real', _get_real, (0,)),
        item(S7WLWord, 12, 'word', _get_word, (0,)),
    ]


def test_every_flavour_reads_the_same_values(flavour):
    name, client = flavour

    read = _raw_reader(client).read_items(_data_items())

    assert {r['key']: r['value'] for r in read} == EXPECTED
    assert all('bt' in r for r in read)
    if name == 'modern-pure-python':  # bits via the byte holding them, no word lengths
        assert client.calls == [
            (0x84, 1, 0, 1), (0x84, 1, 0, 1), (0x84, 1, 3, 1), (0x84, 1, 8, 4), (0x84, 1, 12, 2),
        ]
    else:  # one request for everything, word lengths and bit offsets intact
        assert client.calls == [
            [(1, 1, 1, 1), (1, 1, 0, 1), (2, 1, 3, 1), (8, 1, 8, 1), (4, 1, 12, 1)]
        ]


def test_multi_bit_reads_cross_byte_boundaries_alike(flavour):
    from plcstream2py.raw_plc import PlcDataItem
    from plcstream2py.snap7_compat import S7AreaDB, S7WLBit

    def bits(buffer, byte_index):
        return [buffer[i] for i in range(3)]

    # bits 118, 119 (byte 14) and 120 (byte 15)
    item = PlcDataItem(S7AreaDB, S7WLBit, 1, 14 * 8 + 6, 3, 'bits', bits, (0,))
    read = _raw_reader(flavour[1]).read_items([item])
    assert read[0]['value'] == [1, 1, 1]


def test_a_failed_multi_var_read_gives_none(snap7_layout, monkeypatch):
    compat = importlib.import_module('plcstream2py.snap7_compat')
    monkeypatch.setattr(compat, '_is_pure_python_client', lambda: False)
    client = _NativeClient(MEMORY, status=1)
    assert _raw_reader(client).read_items(_data_items()) is None


def test_a_failed_pure_python_read_raises(monkeypatch):
    class _Failing(_PurePythonClient):
        def read_area(self, area, db_number, start, size, word_len=None):
            raise RuntimeError('boom')

    with snap7_env('modern'):
        compat = importlib.import_module('plcstream2py.snap7_compat')
        monkeypatch.setattr(compat, '_is_pure_python_client', lambda: True)
        with pytest.raises(RuntimeError, match='boom'):
            _raw_reader(_Failing(MEMORY)).read_items(_data_items())


def test_get_info_tolerates_the_clients_errors(snap7_layout):
    from plcstream2py.snap7_compat import SNAP7_ERRORS

    class _Client:
        def get_connected(self):
            return True

        def get_cpu_info(self):
            raise SNAP7_ERRORS[0]('no cpu info')

        def get_cpu_state(self):
            return 'S7CpuStatusRun'

        def get_pdu_length(self):
            raise RuntimeError('no pdu')

    assert _raw_reader(_Client()).get_info() == {'cpu_state': 'S7CpuStatusRun'}


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(INSTALLED_SNAP7_LAYOUT != 'modern', reason='needs python-snap7 3.x')
class TestAgainstSnap7Server:
    """``PlcRawRead`` against the pure-Python S7 server shipped with python-snap7 3.x.

    That server answers every read with byte-typed data, unlike a real PLC (which types
    bit and real answers differently), so this checks the connection, the addressing and
    the decoding, not the wire format of every transport size.
    """

    @pytest.fixture
    def server_port(self, real_snap7):
        if not importlib.util.find_spec('snap7.s7protocol'):
            pytest.skip('this python-snap7 has no pure-Python client and server')
        from snap7.type import SrvArea

        port = _free_port()
        server = real_snap7.Server()
        server.register_area(SrvArea.DB, 1, bytearray(MEMORY[1]))
        server.start_to('127.0.0.1', port)
        try:
            yield port
        finally:
            server.stop()

    def test_read_and_info(self, server_port):
        from plcstream2py.raw_plc import PlcRawRead

        reader = PlcRawRead('127.0.0.1', rack=0, slot=0, tcp_port=server_port)
        assert reader.open()
        try:
            read = reader.read_items(_data_items())
            assert {r['key']: r['value'] for r in read} == EXPECTED
            assert {'cpu_state', 'pdu_len'} <= set(reader.get_info())
        finally:
            reader.close()
