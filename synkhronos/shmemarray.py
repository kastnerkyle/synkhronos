#
# Based on multiprocessing.sharedctypes.RawArray
#
# Uses posix_ipc (http://semanchuk.com/philip/posix_ipc/) to allow shared ctypes arrays
# among unrelated processors
#
# Usage Notes:
#    * The first two args (typecode_or_type and size_or_initializer) should work the same as with RawArray.
#    * The shared array is accessible by any process, as long as tag matches.
#    * The shared memory segment is unlinked when the origin array (that returned
#      by ShmemRawArray(..., create=True)) is deleted/gc'ed
#    * Creating an shared array using a tag that currently exists will raise an ExistentialError
#    * Accessing a shared array using a tag that doesn't exist (or one that has been unlinked) will also
#      raise an ExistentialError
#
# Author: Shawn Chin (http://shawnchin.github.com)
#
# Edited for python 3 by: Adam Stooke
#

import numpy as np
# import os
import sys
import mmap
import ctypes
import posix_ipc
# from _multiprocessing import address_of_buffer  # (not in python 3)
from string import ascii_letters, digits

valid_chars = frozenset("/-_. %s%s" % (ascii_letters, digits))

typecode_to_type = {
    'c': ctypes.c_char, 'u': ctypes.c_wchar,
    'b': ctypes.c_byte, 'B': ctypes.c_ubyte,
    'h': ctypes.c_short, 'H': ctypes.c_ushort,
    'i': ctypes.c_int, 'I': ctypes.c_uint,
    'l': ctypes.c_long, 'L': ctypes.c_ulong,
    'f': ctypes.c_float, 'd': ctypes.c_double
}


def address_of_buffer(buf):  # (python 3)
    return ctypes.addressof(ctypes.c_char.from_buffer(buf))


class ShmemBufferWrapper(object):

    def __init__(self, tag, size, create=True):
        # default vals so __del__ doesn't fail if __init__ fails to complete
        self._mem = None
        self._map = None
        self._owner = create
        self.size = size

        assert 0 <= size < sys.maxsize  # sys.maxint  (python 3)
        flag = (0, posix_ipc.O_CREX)[create]
        self._mem = posix_ipc.SharedMemory(tag, flags=flag, size=size)
        self._map = mmap.mmap(self._mem.fd, self._mem.size)
        self._mem.close_fd()

    def get_address(self):
        # addr, size = address_of_buffer(self._map)
        # assert size == self.size
        assert self._map.size() == self.size  # (changed for python 3)
        addr = address_of_buffer(self._map)
        return addr

    def __del__(self):
        if self._map is not None:
            self._map.close()
        if self._mem is not None and self._owner:
            self._mem.unlink()


def ShmemRawArray(typecode_or_type, size_or_initializer, tag, create=True):
    assert frozenset(tag).issubset(valid_chars)
    if tag[0] != "/":
        tag = "/%s" % (tag,)

    type_ = typecode_to_type.get(typecode_or_type, typecode_or_type)
    if isinstance(size_or_initializer, int):
        type_ = type_ * size_or_initializer
    else:
        type_ = type_ * len(size_or_initializer)

    buffer = ShmemBufferWrapper(tag, ctypes.sizeof(type_), create=create)
    obj = type_.from_address(buffer.get_address())
    obj._buffer = buffer

    if not isinstance(size_or_initializer, int):
        obj.__init__(*size_or_initializer)

    return obj


###############################################################################
#                       New Additions  (by Adam)                              #


NP_TO_C_TYPE = {'float64': ctypes.c_double, np.dtype('float64'): ctypes.c_double,
                'float32': ctypes.c_float, np.dtype('float32'): ctypes.c_float,
                'float16': None, np.dtype('float16'): None,
                'int8': ctypes.c_byte, np.dtype('int8'): ctypes.c_byte,
                'int16': ctypes.c_short, np.dtype('int16'): ctypes.c_short,
                'int32': ctypes.c_int, np.dtype('int32'): ctypes.c_int,
                'int64': ctypes.c_longlong, np.dtype('int64'): ctypes.c_longlong,
                'uint8': ctypes.c_ubyte, np.dtype('uint8'): ctypes.c_ubyte,
                'uint16': ctypes.c_ushort, np.dtype('uint16'): ctypes.c_ushort,
                'uint32': ctypes.c_uint, np.dtype('uint32'): ctypes.c_uint,
                'uint64': ctypes.c_ulonglong, np.dtype('uint64'): ctypes.c_ulonglong,
                }


def NpShmemArray(dtype, shape, tag, create=True):
    ctype = NP_TO_C_TYPE.get(dtype, None)
    if ctype is None:
        raise ValueError("Unsupported numpy dtype: ", dtype)
    shmem = ShmemRawArray(ctype, int(np.prod(shape)), tag, create)
    return np.ctypeslib.as_array(shmem).reshape(shape)
