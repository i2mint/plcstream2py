# plcstream2py.snap7_compat

One place that knows how `python-snap7` is laid out, across its major versions.

`python-snap7` reorganised its public surface between 1.x and 2.x, and again made
the client pure-Python in 3.x:

| layout   | names                         | exceptions                         |
|----------|-------------------------------|------------------------------------|
| legacy   | `snap7.types` (`S7AreaDB`,    | `snap7.exceptions.Snap7Exception`, |
| (1.x)    | `S7WLBit`, …), `snap7.common` | `RuntimeError`                     |
| modern   | `snap7.type` (`Area`,         | `RuntimeError` (and, in 3.x,       |
| (2.x+)   | `WordLen`), `snap7.error`     | `snap7.error.S7Error`)             |

The rest of the package imports the names it needs from here, so supporting a new
`python-snap7` release means touching this module only. Everything is resolved at
import time from what is installed; `SNAP7_LAYOUT` says which layout won.

Reading is the one behavioural difference worth a seam. The legacy and 2.x clients
hand an array of `S7DataItem` to the native library’s multi-variable read, which
honours each item’s `WordLen` (a *bit* item addresses a single bit). The 3.x
client accepts the same array but reads every item as plain bytes, ignoring
`WordLen` – a bit item would silently return the byte at the bit offset – and its
typed `read_area(..., word_len=...)` mis-parses the bit and real answers a PLC
sends (it returns no data). So on the pure-Python 3.x client [`read_data_items()`](#plcstream2py.snap7_compat.read_data_items)
reads plain bytes and does the bit extraction itself; everywhere else it uses
`read_multi_vars`.

The plain-byte reads go out together when the 3.x client has the dict-based
`read_multi_vars` (recognised by its `use_optimizer` attribute): its (experimental)
optimizer merges adjacent items and packs them into few PDUs. Older 3.x clients get
one round trip per item.

### Module Attributes

| [`WORD_LEN_BYTES`](#plcstream2py.snap7_compat.WORD_LEN_BYTES)   | Bytes one element of a given word length occupies in an item's read buffer.   |
|-------------------------------------------------------------------|-------------------------------------------------------------------------------|

### Functions

| [`read_data_items`](#plcstream2py.snap7_compat.read_data_items)(client, items)   | Read an array of `S7DataItem` from `client`; return the array, filled in.   |
|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------------|

### plcstream2py.snap7_compat.WORD_LEN_BYTES *= {1: 1, 2: 1, 4: 2, 6: 4, 8: 8}*

Bytes one element of a given word length occupies in an item’s read buffer.
(`Real` is over-allocated – 8 rather than 4 – as it always was; harmless.)

### plcstream2py.snap7_compat.read_data_items(client, items)

Read an array of `S7DataItem` from `client`; return the array, filled in.

Each item’s `pData` buffer receives its bytes and `Result` its status code
(0 on success), as `Client.read_multi_vars` does. Returns `None` when the
multi-variable read reports a non-zero status; a failed per-item read raises,
as the client’s own errors do.
