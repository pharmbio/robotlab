import show
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
PORT = 30001
JUMPHOST = os.environ['JUMPHOST']

from protocol import protocol, dotdict, formats

print('connecting...')
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
print('connected!')

def try_unpack(data, fields, offset=0):
    if not data[offset:]:
        return None, offset
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
            pp(name, fields, values, e, format, data[offset:])
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

i = 0

while True:

    i += 1
    data = s.recv(4096)
    msgs = []
    stuck = []

    if i % 4 == 2:
        s.sendall(pp(dedent(f'''
          def testsend{i}():
           socket_open("{JUMPHOST}", 32021, "jumphost")
           socket_send_line("i={i}", "jumphost")
           socket_send_line(to_str(get_actual_joint_positions()), "jumphost")
           socket_send_line(to_str(get_actual_joint_speeds()), "jumphost")
           socket_send_line(to_str(get_actual_tool_flange_pose()), "jumphost")
           socket_send_line(to_str(is_steady()), "jumphost")
           socket_close("jumphost")
          end
        ''').strip().encode() + b'\n'))
    if 0:
        s.sendall(pp(dedent(f'''
          def testmove{i}():
           popup("Move to somewhere close to delid neutral?", blocking=True)
           movel([1.544043, -1.830774, 1.472922, 0.346051, 1.88934, 0.04], a=0.1, v=0.1)
          end
        ''').strip().encode() + b'\n'))

    if 0:
        s.sendall(pp(dedent(f'''
          def testmove{i}():
           popup("Start freedrive", blocking=True)
           freedrive_mode()
           popup("Stop freedrive", blocking=True)
           end_freedrive_mode()
          end
        ''').strip().encode() + b'\n'))


    offset = 0
    while True:
        start_offset = offset
        header, values, offset = try_unpacks(data, protocol.types, offset)

        if values is None:
            stuck += [('stuck at', data[offset:][:])]
            break

        elif values['messageType'] == 'MESSAGE_TYPE_ROBOT_STATE':
            size = values['messageSize']
            while offset < start_offset + size:
                subheader, values, offset = try_unpacks(data, protocol.subtypes, offset)
                if values:
                    msgs += [{'header': header, 'subheader': subheader, **values}]
                else:
                    stuck += [('stuck at sub', data[offset:][:])]
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
    # pp(msgs)
    # pp(msgs, stuck)
    # pp(len(msgs), len(flat), len(stuck))
    # pp(keys)
    # pp(keys, flat)
    summary = [(m['header'], m.get('subheader')) for m in msgs ]
    pp(summary)
    pp(flat)
    # for m in msgs:
    #     if m['header'] == 'RobotCommMessage':
    #         pp(m, stuck)

