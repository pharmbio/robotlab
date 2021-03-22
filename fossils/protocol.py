import snoop
from snoop import pp

formats = {
    'byte':               'c',
    'bool':               'b',
    'char':               'c',
    'signed char':        'b',
    'int8_t':             'b',
    'unsigned char':      'B',
    'uint8_t':            'B',
    'short':              'h',
    'int16_t':            'h',
    'unsigned short':     'H',
    'uint16_t':           'H',
    'int':                'i',
    'int32_t':            'i',
    'unsigned int':       'I',
    'uint32_t':           'I',
    'long':               'l',
    'unsigned long':      'L',
    'long long':          'q',
    'int64_t':            'q',
    'unsigned long long': 'Q',
    'uint64_t':           'Q',
    'ssize_t':            'n',
    'size_t':             'N',
    'float':              'f',
    'double':             'd',
    'char[]':             's',
    'void*':              'P',
}

# patch
formats['char'] = formats['unsigned char']
formats['charArray'] = formats['char[]']

class dotdict(dict):
    __getattr__ = dict.get

from collections import defaultdict, OrderedDict
import re

def parse_protocol(content):
    '''
    Parse the protocol from the excel file
    '''
    chunks = content.split('\n\n')
    consts = defaultdict(dict)
    types = {}
    subtypes = {}
    unknowns = {}
    for chunk in chunks:
        chunk0 = chunk

        def with_foreach_body(m):
            lines = m.group(1).split('\n')
            out = []
            for joint in range(6):
                for line in lines:
                    out += [line + '[' + str(joint) + ']']
            return '\n'.join(out)
        multi = re.MULTILINE | re.DOTALL
        chunk = re.sub(r'^for each joint:\n(.*?)\n^end', with_foreach_body, chunk, flags=multi)
        chunk = re.sub(r'^for each joint:\n(.*?)(?=\n)', with_foreach_body, chunk, flags=multi)

        lines = chunk.split('\n')
        fields = []
        header = None
        unknown = []
        for line in lines:
            ctypes = sorted(formats.keys(), key=lambda ctype: -len(ctype))
            for ctype in ctypes:
                if line.startswith(ctype + ' '):
                    rest = line[len(ctype + ' '):]
                    name, *parts = [part.strip() for part in rest.split('=')]
                    required_value = None
                    if len(parts) == 2:
                        const, required_value = parts
                        required_value = int(required_value)
                        consts[name][const] = required_value
                    elif len(parts) == 1:
                        required_value, = parts
                        required_value = int(required_value)
                    # Fix some typos
                    name = re.sub(r'Limitt\b',  'Limit', name)
                    name = re.sub(r'cheksum\b', 'checksum', name)
                    name = re.sub(' ', '_', name)
                    fields += [(name, (ctype, required_value))]
                    break
            else:
                if header is None:
                    header = line
                    header = header.split('(')[0].strip()
                else:
                    unknown += [line]
        if len(fields) == 0:
            continue

        message_type = dict(fields).get('robotMessageType', 'xx')[1]
        version_type = consts['robotMessageType'].get('ROBOT_MESSAGE_TYPE_VERSION')
        VersionMessage = message_type == version_type
        if header is None and VersionMessage:
            header = 'VersionMessage'
        if header is None:
            pp(header, fields)
            raise ValueError('Add manual header for these lines:\n' + '\n'.join(lines))
        if unknown:
            unknowns[header] = '\n'.join(unknown)
        header = header.replace('Robot message - ', '')
        header = header.replace('Robot Message - ', '')
        fields = dict(fields)
        if 'messageType' in fields:
            types[header] = fields
        elif 'packageType' in fields:
            subtypes[header] = fields
        else:
            pp(header, fields)
            raise ValueError('What is this? ' + header)

    return dotdict(
        types=types,
        subtypes=subtypes,
        consts={
            field_name: {value: name for name, value in values.items()}
            for field_name, values in consts.items()
        },
        unknowns=unknowns,
    )

protocol = parse_protocol(open('client-interface-5.6.txt').read())

pp(protocol.consts)
pp(protocol.unknowns)
pp(protocol.types)
pp(protocol.subtypes)

for hdr, fields in protocol.types.items():
    ctype, default = fields['messageType']
    if default is None:
        pp(hdr, fields)
        raise ValueError('Missing messageType on this ' + hdr)

for hdr, fields in protocol.subtypes.items():
    ctype, default = fields['packageType']
    if default is None:
        pp(hdr, fields)
        raise ValueError('Missing packageType on this ' + hdr)

fmts = dict(
  # VersionMessage='!iBQBBB63sBBii42s',

  RobotStateMessage='!iB',
  RobotModeData='!iBQbbbbbbbBBdddB',

  JointData='!iBdddffffBdddffffBdddffffBdddffffBdddffffBdddffffB',
  CartesianInfo='!iBdddddddddddd',
  KinematicsInfo='!iBIIIIIIddddddddddddddddddddddddI',

  # CalibrationData='!iBdddddd',
  # MasterboardData='!iBiiBBddBBddffffBBBIIffBBB',

  KeyMessage                  ='!iBQBBiiBs',
  GlobalVariablesUpdateMessage='!iBQBHB',
  RobotCommMessage            ='!iBQBBiiiIIs',
  SafetyModeMessage           ='!iBQBBiiBII',
  RuntimeExceptionMessage     ='!iBQBBiis',

  # For some reason this is what is sent on popup:
  RequestValueMessage         ='!iBQBBIBB',

)

# errors look like RuntimeExceptionMessage with:
# b'syntax_error_on_line:4:    movej([0.5, -1, -2, 0, 0, -0], a=0.25, v=1.0):'
# b'compile_error_name_not_found:getactual_joint_positions:'

# KeyMessage
# PROGRAM_XXX_STARTED
# PROGRAM_XXX_STOPPED

def try_unpack(data, fields, offset=0):
    if not data[offset:]:
        return None, offset, None
    start_offset = offset
    values = {}

    f_str = '!'

    # print(data)
    for name, (ctype, required_value) in fields.items():
        format = formats[ctype]
        str_format = False
        if format == 's':
            str_format = True
            format = str(len(data) - offset) + format
        f_str += format
        format = '!' + format
        try:
            value, = struct.unpack_from(format, data, offset)
        except ValueError as e:
            # pp(e, format, data, offset)
            return None, start_offset, None
        except Exception as e:
            return None, start_offset, None
            # pp(name, fields, values, e, format, data[start_offset:])
            # raise e
        if str_format:
            value, *_ = value.split(b'\x00', 1)
            offset += len(value)
        else:
            offset += struct.calcsize(format)
        if required_value is not None:
            if value != required_value:
                return None, start_offset, None
            else:
                pass
                # pp(format, value, required_value, name, offset)
                # pp(fields, values)
        values[name] = value
        const = protocol.consts.get(name, {}).get(value, None)
        if const:
            values[name] = const

    # if f_str not in fmts:
        # H = values.get('header'), values.get('subheader')
        # fmts[f_successes.add(pp(f_str))

    return values, offset, f_str

def try_unpacks(data, types, offset=0):
    start_offset = offset
    for header, fields in types.items():
        values, offset, fmt = try_unpack(data, fields, start_offset)
        if values is not None:
            if header not in fmts:
                fmts[header] = fmt
                pp(fmts)
            return header, values, offset
    return None, None, start_offset

def parse(data):
    msgs = []
    stuck = []

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
    return msgs, stuck

prev_flat = {}
def output(msgs, stuck):
    global prev_flat
    keys = {
        re.sub('\[\d\]', '[]', k)
        for m in msgs for k in m.keys()
        if '(' not in k
    }
    keys = ' '.join(sorted(keys))
    all = {
        k: v for m in msgs for k, v in m.items()
    }
    flat = {
        k: v for m in msgs for k, v in m.items()
        if any([
          # re.match('[XYZ]|R[xyz]', k),
          not re.search('(^[VFI])|motor|Current|Limit|V$|qd?d?_actual|Temperature', k),
          re.search('^is|Mode$', k),
          # re.search('^is|Mode$', k),
          # re.search('^isProgram|Mode$', k),
        ])
    }
    q = [ all.get(f'q_actual[{i}]') for i in range(6) ]
    qd = [ all.get(f'qd_actual[{i}]') for i in range(6) ]

    summary = [(m['header'], m.get('subheader')) for m in msgs ]

    for m in msgs:
        # if m['header'] in 'TextMessage KeyMessage GlobalVariablesUpdateMessage'.split():
        if re.search('\w(?<!GlobalVariablesUpdate)Message$', m['header']):
            pp(m)

    # if stuck:
        # pp(stuck)

    if None in q:
        pass
        # pp(stuck)
        # for m in msgs:
            # pp(m)
        # if len(summary):
            # pp(summary, len(stuck))
    else:
        for k, v in flat.items():
            if re.match('[XYZ]', k):
                flat[k] = v * 1000
            if re.match('q_|R', k):
                flat[k] = v * (180 / math.pi)
        for k, v in flat.items():
            if isinstance(v, float):
                r = round(v, 0 if k in 'XYZ' else 1)
                if r == -0.0:
                    r = 0.0
                flat[k] = r
        flat['q']  = [ round(v, 3) if v else v for v in q  ]
        flat['qd'] = [ round(v, 3) if v else v for v in qd ]
        flat['summary'] = summary
        # pp(msgs)
        # pp(msgs, stuck)
        # pp(len(msgs), len(flat), len(stuck))
        # pp(keys)
        # pp(keys, flat)
        changes = {}
        for k in prev_flat.keys() | flat.keys():
            if prev_flat.get(k) != flat.get(k):
                changes[k] = flat.get(k)
        if changes:
            pass
            # pp(fmts)
            # pp(changes)
        prev_flat = flat

    # for m in msgs:
    #     if m['header'] == 'RobotCommMessage':
    #         pp(m, stuck)


