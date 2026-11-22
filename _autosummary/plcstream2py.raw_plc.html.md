# plcstream2py.raw_plc

Thin, snap7-level access to values stored in a Siemens S7 PLC.

[`PlcDataItem`](#plcstream2py.raw_plc.PlcDataItem) describes a single value to read – where it lives in the PLC
(area, word length, DB number, start offset, amount) and how to turn the bytes that
come back into a Python value. `PlcRawRead` connects to a PLC and reads a list
of those items in one multi-variable request.

It works with `python-snap7` 1.x, 2.x and 3.x: the names that moved between them
come from [`plcstream2py.snap7_compat`](plcstream2py.snap7_compat.html.md#module-plcstream2py.snap7_compat). [`plcstream2py.plc`](plcstream2py.plc.html.md#module-plcstream2py.plc) builds the
streaming interface on top of it.

### Functions

| [`get_byte`](#plcstream2py.raw_plc.get_byte)(_bytearray, byte_index)   | Get the boolean value from location in bytearray   |
|-------------------------------------------------------------------------------------|----------------------------------------------------|

### Classes

| [`PlcDataItem`](#plcstream2py.raw_plc.PlcDataItem)(area, word_len, db_number, ...)   |    |
|------------------------------------------------------------------------------------------------|----|
| `PlcRawRead`(ip_address, \*, rack, slot[, tcp_port])                                           |    |

### *class* plcstream2py.raw_plc.PlcDataItem(area, word_len, db_number, start, amount, key, convert, convert_args=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

### plcstream2py.raw_plc.get_byte(\_bytearray, byte_index)

Get the boolean value from location in bytearray
