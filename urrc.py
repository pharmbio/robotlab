import show

import snoop
from snoop import pp

from textwrap import dedent
import socket
import re
import math
import ast

# Use start-proxies.sh to forward robot to localhost
HOST = 'localhost'
PORT = 30001

print('connecting...')
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
print('connected!')

i = 0
while True:

    i += 1
    data = s.recv(4096)

    # TextMessage, they are from urscript textmsg.
    # Can also be seen in the log on the polyscope (the ui on the tablet aka teach pendant)
    for m in re.findall(b'<msg>(.*?)</msg>', data):
        m = ast.literal_eval(m.decode())
        print(m)


    # RuntimeExceptionMessage, looks like:
    # b'syntax_error_on_line:4:    movej([0.5, -1, -2, 0, 0, -0], a=0.25, v=1.0):'
    # b'compile_error_name_not_found:getactual_joint_positions:'
    # b'SECONDARY_PROGRAM_EXCEPTION_XXXType error: str_sub takes exact'
    for m in re.findall(b'([\x20-\x7e]*(?:error|EXCEPTION)[\x20-\x7e]*)', data):
        m = m.decode()
        pp(m)

    # KeyMessage, looks like:
    # PROGRAM_XXX_STARTEDtestmove2910
    # PROGRAM_XXX_STOPPEDtestmove2910
    for m in re.findall(b'PROGRAM_XXX_(\w*)', data):
        m = m.decode()
        pp(m)

    if 0:
        for m in re.findall(b'([\x20-\x7e]{10,})', data):
            if len(set(m)) > 3:
                print('printable', m)

    def send(program_str):
        p = dedent(program_str).strip()
        # print(p.split('\n')[0])
        s.sendall(p.encode() + b'\n')


    if i % 4 == 3:
         send(f'''
          sec text_pq{i}():
           p = str_sub(to_str(get_actual_tool_flange_pose()),1)
           q = to_str(get_actual_joint_positions())
           xs = ""
           xs = str_cat(str_cat(xs, is_steady()), ",")
           xs = str_cat(str_cat(xs, q), ",")
           xs = str_cat(str_cat(xs, p), ",")
           textmsg("<msg>[", str_cat(xs, "]</msg>"))
          end
        ''')

    if 0:
        if i % 100 = 10:
            send(f'''
              def testmove{i}():
                q = get_actual_joint_positions()
                if q[0] > 1:
                  movej([0.5, -1, -2, 0, 0, -0], a=1.0, v=1.0)
                else:
                  movej([1.2, -1, -2, 0, 0, -0], a=1.0, v=1.0)
                end
              end
            ''')

    if 0:
        send(f'''
          def testmove{i}():
           popup("Move to somewhere close to delid neutral?", blocking=True)
           movel([1.544043, -1.830774, 1.472922, 0.346051, 1.88934, 0.04], a=0.1, v=0.1)
          end
        ''')

    if 0:
        send(f'''
          def testfreedrive{i}():
           popup("Start freedrive", blocking=True)
           freedrive_mode()
           popup("Stop freedrive", blocking=True)
           end_freedrive_mode()
          end
        ''')

