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
``WordLen`` -- a bit item would silently return the byte at the bit offset. So
:func:`read_data_items` reads item by item through ``Client.read_area(...,
word_len=...)`` whenever the client supports that, and uses ``read_multi_vars``
otherwise.
"""

import inspect
from importlib import import_module

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


def _read_area_takes_word_len(client) -> bool:
    """Whether ``client.read_area`` can be told the word length (python-snap7 3.x)."""
    try:
        return 'word_len' in inspect.signature(client.read_area).parameters
    except (AttributeError, TypeError, ValueError):
        return False


def _read_item_via_read_area(client, item) -> None:
    """Fill ``item.pData`` using ``read_area``, honouring the item's word length."""
    data = client.read_area(
        _types.Area(item.Area),
        item.DBNumber,
        item.Start,
        item.Amount,
        word_len=_types.WordLen(item.WordLen),
    )
    capacity = WORD_LEN_BYTES[item.WordLen] * item.Amount
    for index, byte in enumerate(bytes(data)[:capacity]):
        item.pData[index] = byte
    item.Result = 0


def read_data_items(client, items):
    """Read an array of ``S7DataItem`` from ``client``; return the array, filled in.

    Each item's ``pData`` buffer receives its bytes and ``Result`` its status code
    (0 on success), as ``Client.read_multi_vars`` does. Returns ``None`` when the
    multi-variable read reports a non-zero status; a failed per-item read raises,
    as the client's own errors do.
    """
    if _read_area_takes_word_len(client):
        for item in items:
            _read_item_via_read_area(client, item)
        return items
    result, items_read = client.read_multi_vars(items)
    return None if result else items_read
