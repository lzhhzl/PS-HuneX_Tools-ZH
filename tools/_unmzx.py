#!/usr/bin/env python

import os
import shutil
from sys import stderr
from struct import unpack
from pathlib import Path
from mzx.decomp_mzx0 import mzx0_decompress

for file_path in Path().glob('**/*.[Mm][Zz][Xx]'):
    out_path = file_path.with_suffix('.ini')
    with file_path.open('rb') as data:
        offset = 7 if(data.read(2) == b'LV') else 0
        data.seek(offset)
        sig, size = unpack('<LL', data.read(0x8))
        status, dec_buf = mzx0_decompress(data, os.path.getsize(file_path) - 8 - offset, size, True)
        if status != "OK":
            print("[{0}] {1}".format(file_path, status), file=stderr)
        with out_path.open('wb') as dbg:
            shutil.copyfileobj(dec_buf, dbg)
