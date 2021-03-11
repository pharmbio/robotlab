import socket
import struct
from textwrap import dedent
import snoop
from snoop import pp
import re
import math

import os

# Use start-proxies.sh to forward robot to localhost
HOST = 'localhost'
PORT = 30002

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
i = 0
cw = True

from protocol import protocol, dotdict, formats

def try_unpack(data, fields, offset=0):
    start_offset = offset
    values = {}

    # print(data)
    for name, (ctype, required_value) in fields.items():
        format = formats[ctype]
        str_format = False
        if format == 's':
            str_format = True
            format = str(len(data) - offset) + format
        format = '!' + format
        try:
            value, = struct.unpack_from(format, data, offset)
        except ValueError as e:
            pp(e, format, data, offset)
            return None, start_offset
        except Exception as e:
            pp(name, fields)
            pp(e, format, data[offset:])
            raise e
        if str_format:
            value, *_ = value.split(b'\x00', 1)
            offset += len(value)
        else:
            offset += struct.calcsize(format)
        if required_value is not None:
            if value != required_value:
                return None, start_offset
            else:
                pass
                # pp(format, value, required_value, name, offset)
                # pp(fields, values)
        values[name] = value
        const = protocol.consts.get(name, {}).get(value, None)
        if const:
            values[name] = const

    return values, offset

def try_unpacks(data, types, offset=0):
    start_offset = offset
    for header, fields in types.items():
        values, offset = try_unpack(data, fields, start_offset)
        if values is not None:
            return header, values, offset
    return None, None, start_offset

while True:

    i += 1
    data = s.recv(4096)
    msgs = []
    stuck = []

    offset = 0
    while True:
        start_offset = offset
        header, values, offset = try_unpacks(data, protocol.types, offset)

        if values is None:
            stuck += [('stuck at', data[offset:][:16])]
            break

        elif values['messageType'] == 'MESSAGE_TYPE_ROBOT_STATE':
            size = values['messageSize']
            while offset < start_offset + size:
                subheader, values, offset = try_unpacks(data, protocol.subtypes, offset)
                if values:
                    msgs += [{'header': header, 'subheader': subheader, **values}]
                else:
                    stuck += [('stuck at sub', data[offset:][:16])]
                    break

        else:
            msgs += [{'header': header, **values}]

    keys = {
        re.sub('\[\d\]', '[]', k)
        for m in msgs for k in m.keys()
        if '(' not in k
    }
    keys = ' '.join(sorted(keys))
    flat = {
        k: v for m in msgs for k, v in m.items()
        if re.match('q_actual|R?[xyzXYZ]', k)
        #|robot|(?<!joint)Mode|is|speed|control', k)
    }
    for k, v in flat.items():
        if re.match('[XYZ]', k):
            flat[k] = v * 1000
        if re.match('q_|R', k):
            flat[k] = v * (180 / math.pi)
    for k, v in flat.items():
        if isinstance(v, float):
            r = round(v, 1)
            if r == -0.0:
                r = 0.0
            flat[k] = r
    pp(keys, flat, len(msgs), len(flat), len(stuck))
    # summary = [(m['header'], m.get('subheader')) for m in msgs ]
    # pp(summary)

