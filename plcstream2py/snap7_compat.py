"""One place that knows how ``python-snap7`` is laid out, across its major versions.

``python-snap7`` reorganised its public surface between 1.x and 2.x, and again made
the client pure-Python in 3.x:

========  ====================================  ================================
 layout    names                                 exceptions
========  ====================================  ================================
 legacy    ``snap7.types`` (``S7AreaDB``,        ``snap7.exceptions.Snap7Exception``,
 (1.x)     ``S7WLBit``, ...), ``snap7.common``   ``RuntimeError``
 modern    ``snap7.type`` (``Area``,             ``RuntimeError`` (and, in 3.x,
 (2.x+)    ``WordLen``), ``snap7.error``         ``snap7.error.S7Error``)
========  ====================================  ================================

The rest of the package imports the names it needs from here, so supporting a new
``python-snap7`` release means touching this module only. Everything is resolved at
import time from what is installed; :data:`SNAP7_LAYOUT` says which layout won.

Reading is the one behavioural difference worth a seam. The legacy and 2.x clients
hand an array of ``S7DataItem`` to the native library's multi-variable read, which
honours each item's ``WordLen`` (a *bit* item addresses a single bit). The 3.x
client accepts the same array but reads every item as plain bytes, ignoring
``WordLen`` -- a bit item would silently return the byte at the bit offset -- and its
typed ``read_area(..., word_len=...)`` mis-parses the bit and real answers a PLC
sends (it returns no data). So on the pure-Python 3.x client :func:`read_data_items`
reads plain bytes and does the bit extraction itself; everywhere else it uses
``read_multi_vars``.

The plain-byte reads go out together when the 3.x client has the dict-based
``read_multi_vars`` (recognised by its ``use_optimizer`` attribute): its (experimental)
optimizer merges adjacent items and packs them into few PDUs. Older 3.x clients get
one round trip per item.
"""

from importlib import import_module
from importlib.util import find_spec

import snap7

try:  # python-snap7 >= 2
    _types = import_module('snap7.type')
    _error = import_module('snap7.error')
except ModuleNotFoundError as _exc:
    if _exc.name not in ('snap7.type', 'snap7.error'):
        raise
    _types = import_module('snap7.types')
    _error = import_module('snap7.common')
    SNAP7_LAYOUT = 'legacy'
    S7AreaDB = _types.S7AreaDB
    S7WLBit = _types.S7WLBit
    S7WLByte = _types.S7WLByte
    S7WLWord = _types.S7WLWord
    S7WLDWord = _types.S7WLDWord
    S7WLReal = _types.S7WLReal
    _legacy_exception = import_module('snap7.exceptions').Snap7Exception
    #: Exceptions the client raises for a failed call (what ``get_info`` tolerates).
    SNAP7_ERRORS = (_legacy_exception, RuntimeError)
else:
    SNAP7_LAYOUT = 'modern'
    # plain ints: they are stored in ctypes fields and compared with ``in`` / ``==``
    S7AreaDB = int(_types.Area.DB)
    S7WLBit = int(_types.WordLen.Bit)
    S7WLByte = int(_types.WordLen.Byte)
    S7WLWord = int(_types.WordLen.Word)
    S7WLDWord = int(_types.WordLen.DWord)
    S7WLReal = int(_types.WordLen.Real)
    SNAP7_ERRORS = (RuntimeError, *filter(None, [getattr(_error, 'S7Error', None)]))

S7DataItem = _types.S7DataItem
check_error = _error.check_error

#: Bytes one element of a given word length occupies in an item's read buffer.
#: (``Real`` is over-allocated -- 8 rather than 4 -- as it always was; harmless.)
WORD_LEN_BYTES = {S7WLBit: 1, S7WLByte: 1, S7WLWord: 2, S7WLDWord: 4, S7WLReal: 8}


#: Bytes one element occupies on the wire (differs from the buffer size for ``Real``).
_WIRE_BYTES = {S7WLBit: 1, S7WLByte: 1, S7WLWord: 2, S7WLDWord: 4, S7WLReal: 4}


def _is_pure_python_client() -> bool:
    """Whether ``snap7`` is the 3.x line, whose client speaks S7 in pure Python.

    ``snap7.s7protocol`` exists there and nowhere else, and it is that protocol
    implementation that makes ``read_multi_vars`` blind to word lengths.
    """
    try:
        return find_spec('snap7.s7protocol') is not None
    except (ImportError, ValueError):
        return False


def _supports_batched_reads(client) -> bool:
    """Whether ``client.read_multi_vars`` takes dict requests (python-snap7 >= 3.2)."""
    return hasattr(client, 'use_optimizer')


def _byte_request(item) -> tuple[int, int]:
    """``(byte offset, byte count)`` that carries ``item`` on a plain byte read."""
    if item.WordLen == S7WLBit:
        if item.Amount != 1:
            raise ValueError(f'a bit item reads exactly one bit, not {item.Amount}')
        return item.Start // 8, 1
    return item.Start, _WIRE_BYTES[item.WordLen] * item.Amount


def _fill_item(item, data) -> None:
    """Fill ``item.pData`` from the plain bytes ``data`` read for :func:`_byte_request`."""
    if item.WordLen == S7WLBit:
        size, values = 1, [data[0] >> item.Start % 8 & 1] if len(data) else []
    else:
        size, values = _WIRE_BYTES[item.WordLen] * item.Amount, bytes(data)
    if len(values) < size:
        raise RuntimeError(f'expected {size} bytes from the PLC, got {len(values)}')
    for index, byte in enumerate(values[:size]):
        item.pData[index] = byte
    item.Result = 0


def _read_items_batched(client, items) -> None:
    """Read all ``items`` as plain bytes through the 3.x dict-based ``read_multi_vars``.

    Requests go out in chunks of the client's ``MAX_VARS``; each chunk's answers come
    back in request order.
    """
    chunk = getattr(client, 'MAX_VARS', 20)
    items = list(items)
    for lo in range(0, len(items), chunk):
        batch = items[lo : lo + chunk]
        requests = []
        for item in batch:
            start, size = _byte_request(item)
            requests.append(
                {
                    'area': _types.Area(item.Area),
                    'db_number': item.DBNumber,
                    'start': start,
                    'size': size,
                }
            )
        _, answers = client.read_multi_vars(requests)
        for item, data in zip(batch, answers):
            _fill_item(item, data)


def _read_item_as_bytes(client, item) -> None:
    """Fill ``item.pData`` from plain byte reads, as the native word-length-aware read would.

    For a bit item, ``Start`` is a bit offset and the one bit lands in the first buffer
    byte as 0/1 (the S7 protocol allows a single bit per item, and the native library
    rejects more). For the rest, ``Start`` is a byte offset and the ``Amount`` elements'
    bytes are copied as the PLC sent them.
    """
    start, size = _byte_request(item)
    _fill_item(item, client.read_area(_types.Area(item.Area), item.DBNumber, start, size))


def read_data_items(client, items):
    """Read an array of ``S7DataItem`` from ``client``; return the array, filled in.

    Each item's ``pData`` buffer receives its bytes and ``Result`` its status code
    (0 on success), as ``Client.read_multi_vars`` does. Returns ``None`` when the
    multi-variable read reports a non-zero status; a failed per-item read raises,
    as the client's own errors do.
    """
    if _is_pure_python_client():
        if _supports_batched_reads(client):
            _read_items_batched(client, items)
            return items
        for item in items:
            _read_item_as_bytes(client, item)
        return items
    result, items_read = client.read_multi_vars(items)
    return None if result else items_read
