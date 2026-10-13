"""Tests for reading items through :mod:`plcstream2py.raw_plc`, on every snap7 layout.

No PLC exists in CI, so the client is a recording fake injected into ``PlcRawRead``.
What these tests pin down is the part that differs between ``python-snap7`` releases:

- 1.x and 2.x: one ``read_multi_vars`` call, in which each item's ``WordLen`` is
  honoured by the native library;
- 3.x: ``read_multi_vars`` ignores ``WordLen`` (a bit item would read the byte at the
  bit offset), so each item is read with ``read_area(..., word_len=...)``.

:class:`TestAgainstSnap7Server` goes further when ``python-snap7`` 3.x is installed:
it talks to the pure-Python S7 server that ships with it, over loopback.
"""

import inspect
import socket

import pytest

from conftest import INSTALLED_SNAP7_LAYOUT

#: What the fake PLC holds: DB 1, byte 0 = 0b10 (bit 0 clear, bit 1 set).
MEMORY = {1: bytearray([0b10, 0, 0, 77, 200])}


def _get_bool(buffer, byte_index, bool_index):
    """Same contract as ``snap7.util.get_bool``; local so the stand-in util is moot."""
    return bool(buffer[byte_index] >> bool_index & 1)


class _MultiVarsClient:
    """Fake of the 1.x/2.x client: ``read_multi_vars`` fills the buffers itself."""

    def __init__(self, memory, *, status=0):
        self.memory, self.status, self.calls = memory, status, []

    def read_area(self, area, db_number, start, size):  # no ``word_len`` parameter
        raise AssertionError('the multi-variable path must not use read_area')

    def read_multi_vars(self, items):
        self.calls.append([(i.WordLen, i.DBNumber, i.Start, i.Amount) for i in items])
        for item in items:
            if item.WordLen == 0x01:  # native behaviour: a bit item addresses one bit
                byte, bit = divmod(item.Start, 8)
                item.pData[0] = self.memory[item.DBNumber][byte] >> bit & 1
            else:
                for i in range(item.Amount):
                    item.pData[i] = self.memory[item.DBNumber][item.Start + i]
            item.Result = 0
        return self.status, items


class _ReadAreaClient:
    """Fake of the 3.x client: ``read_multi_vars`` drops word lengths, ``read_area`` honours them."""

    def __init__(self, memory):
        self.memory, self.calls = memory, []

    def read_multi_vars(self, items):
        raise AssertionError('the word-length-blind multi-variable read must not be used')

    def read_area(self, area, db_number, start, size, word_len=None):
        self.calls.append((int(area), db_number, start, size, int(word_len)))
        if int(word_len) == 0x01:
            byte, bit = divmod(start, 8)
            return bytearray([self.memory[db_number][byte] >> bit & 1])
        return bytearray(self.memory[db_number][start : start + size])


def _raw_reader(client):
    from plcstream2py.raw_plc import PlcRawRead

    reader = PlcRawRead('127.0.0.1', rack=0, slot=0)
    reader._plc = client
    return reader


def _data_items():
    from plcstream2py.raw_plc import PlcDataItem, get_byte
    from plcstream2py.snap7_compat import S7AreaDB, S7WLBit, S7WLByte

    return [
        PlcDataItem(S7AreaDB, S7WLBit, 1, 0 * 8 + 1, 1, 'led', _get_bool, (0, 0)),
        PlcDataItem(S7AreaDB, S7WLBit, 1, 0 * 8 + 0, 1, 'motor', _get_bool, (0, 0)),
        PlcDataItem(S7AreaDB, S7WLByte, 1, 3, 1, 'speed', get_byte, (0,)),
    ]


def test_items_are_read_with_their_word_length(snap7_layout):
    legacy = snap7_layout == 'legacy'
    client = _MultiVarsClient(MEMORY) if legacy else _ReadAreaClient(MEMORY)

    read = _raw_reader(client).read_items(_data_items())

    assert {r['key']: r['value'] for r in read} == {
        'led': True,
        'motor': False,
        'speed': 77,
    }
    assert all('bt' in r for r in read)
    if legacy:  # one request for everything
        assert client.calls == [[(1, 1, 1, 1), (1, 1, 0, 1), (2, 1, 3, 1)]]
    else:  # one read per item, bit items addressed by bit offset and word length
        assert client.calls == [(0x84, 1, 1, 1, 1), (0x84, 1, 0, 1, 1), (0x84, 1, 3, 1, 2)]


def test_a_failed_multi_var_read_gives_none(stubbed_snap7):
    if stubbed_snap7 != 'legacy':
        pytest.skip('only the multi-variable path reports a status code')
    assert _raw_reader(_MultiVarsClient(MEMORY, status=1)).read_items(_data_items()) is None


def test_a_failed_per_item_read_raises(stubbed_snap7):
    if stubbed_snap7 != 'modern':
        pytest.skip('only the per-item path raises')

    class _Failing(_ReadAreaClient):
        def read_area(self, area, db_number, start, size, word_len=None):
            raise RuntimeError('boom')

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

    Byte items only: that server answers a bit read with the whole byte, where a real
    PLC returns the bit; bit addressing is covered by the fake clients above.
    """

    @pytest.fixture
    def server_port(self, real_snap7):
        if 'word_len' not in inspect.signature(real_snap7.Client.read_area).parameters:
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
        from plcstream2py.raw_plc import PlcDataItem, PlcRawRead, get_byte
        from plcstream2py.snap7_compat import S7AreaDB, S7WLByte

        reader = PlcRawRead('127.0.0.1', rack=0, slot=0, tcp_port=server_port)
        assert reader.open()
        try:
            items = [
                PlcDataItem(S7AreaDB, S7WLByte, 1, 3, 1, 'speed', get_byte, (0,)),
                PlcDataItem(S7AreaDB, S7WLByte, 1, 4, 1, 'brightness', get_byte, (0,)),
            ]
            read = reader.read_items(items)
            assert {r['key']: r['value'] for r in read} == {'speed': 77, 'brightness': 200}
            assert {'cpu_state', 'pdu_len'} <= set(reader.get_info())
        finally:
            reader.close()
