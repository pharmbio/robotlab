
import snoop
from snoop import pp
from pprint import pprint, pformat

pprint.__kwdefaults__['sort_dicts'] = False
pformat.__kwdefaults__['sort_dicts'] = False

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

