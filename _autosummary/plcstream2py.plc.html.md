# plcstream2py.plc

A `stream2py` source reader for Siemens S7 PLC data.

[`PlcReader`](#plcstream2py.plc.PlcReader) wraps `plcstream2py.raw_plc.PlcRawRead` in a
`stream2py.SourceReader`: opening it starts a background thread that polls the PLC
for a fixed list of [`plcstream2py.raw_plc.PlcDataItem`](plcstream2py.raw_plc.html.md#plcstream2py.raw_plc.PlcDataItem) values, and `read`
pops the readings that have accumulated since the last call.

Importing this module needs `python-snap7` (which wraps the native `snap7`
library); reading anything from it also needs a reachable PLC.

### Classes

| [`PlcReader`](#plcstream2py.plc.PlcReader)(ip_address, \*, items_to_read, ...)   |    |
|--------------------------------------------------------------------------------------------------|----|

### *class* plcstream2py.plc.PlcReader(ip_address, , items_to_read, rack, slot, tcp_port=102, sleep_time=1.0)

Bases: `SourceReader`

#### MIN_RETRY_WAIT_S *= 0.1*

Least wait (s) after a failed poll, so `sleep_time=0` cannot spin on errors.

#### close()

Close and clean up source reader.
Will be called when StreamBuffer stops or if an exception is raised during read and append loop.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### *property* info *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

A dict with important source info. Default can be init_kwargs and open timestamp.

This info will be available in BufferReader after SourceReader has opened but any changes
made between open and close are not guaranteed to be visible. Any continuous status updates
should be included with read data instead.

* **Returns:**
  dict

#### key(data_item)

Converts data into a comparable value to sort by

* **Parameters:**
  **data** – the return value of the ‘read’ method
* **Return type:**
  `ComparableType`
* **Returns:**
  ComparableType

#### open()

Set up source to be read and set some source info affected by open time like the time of
open. Will be called in StreamBuffer immediately before first read.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### read(blocking=False, timeout=0)

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
* **Returns:**
  timestamp, plc info, read db items as key:value

#### *property* sleep_time_on_read_none_s *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Sets default sleep time for StreamBuffer when it reads None from SourceReader.
Useful when you know the period between data points.

For example if data only comes once every 10 seconds,
it would be inefficient to try and read again every 0.1 seconds and get None up to 100 times
but every 10 seconds or even 1 second would be much more reasonable depending on the use
case. Not necessary if read is a blocking function that always returns a data point.

Default is None which delegates the sleep time to StreamBuffer’s default.

* **Returns:**
  Optional[Union[int, float]] number of seconds to sleep
