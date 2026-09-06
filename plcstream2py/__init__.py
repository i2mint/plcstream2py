"""stream2py interface to Siemens S7 PLC data.

Two layers, from low to high:

- :mod:`plcstream2py.raw_plc`: a thin wrapper over ``python-snap7``. ``PlcDataItem``
  describes one value to read from a PLC (area, word length, DB number, offset, and
  how to decode the bytes); ``PlcRawRead`` connects to a PLC and reads a list of them.
- :mod:`plcstream2py.plc`: ``PlcReader``, a ``stream2py.SourceReader`` that polls a
  ``PlcRawRead`` on a background thread so PLC readings can be consumed as a stream.

Both layers need ``python-snap7``, which wraps the native ``snap7`` library, so they
are not imported here: ``import plcstream2py`` stays free of that dependency.
"""
