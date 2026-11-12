"""Test-only descriptor loader for the checked-in proto2 map schemas.

Allows real protobuf serialization/oneof assertions when protoc is unavailable.
Production continues to use Apollo-generated *_pb2 modules. This deliberately
supports only the message/enum/oneof syntax used by map.proto and its imports.
"""
import re
import sys
import types
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def load_map_protos(root):
    files, symbols, unresolved = {}, {}, []
    scalar = {n.removeprefix('TYPE_').lower(): v for n, v in descriptor_pb2.FieldDescriptorProto.Type.items()}

    def parse(path):
        if path in files:
            return
        content = re.sub(r'//[^\n]*|/\*.*?\*/', '', (root / path).read_text(), flags=re.S)
        file = descriptor_pb2.FileDescriptorProto(name=path, syntax='proto2')
        files[path] = file
        file.package = re.search(r'package\s+([\w.]+)', content)[1]
        for dep in re.findall(r'import\s+"([^"]+)"', content):
            file.dependency.append(dep)
            parse(dep)
        tokens = re.findall(r'"[^"\\]*(?:\\.[^"\\]*)*"|[.\w+-]+|[^\s]', content)
        pos = 0

        def block(owner, scope, kind='file', oneof=None):
            nonlocal pos
            while pos < len(tokens):
                token = tokens[pos]; pos += 1
                if token == '}':
                    return
                if token in ('message', 'enum'):
                    name = tokens[pos]; pos += 1
                    assert tokens[pos] == '{'; pos += 1
                    if token == 'message':
                        seq = owner.message_type if kind == 'file' else owner.nested_type
                        child = seq.add(name=name)
                    else:
                        child = owner.enum_type.add(name=name)
                    symbols[scope+'.'+name] = token
                    block(child, scope+'.'+name, token)
                elif token == 'oneof':
                    index = len(owner.oneof_decl)
                    owner.oneof_decl.add(name=tokens[pos]); pos += 2
                    block(owner, scope, 'oneof', index)
                elif token in ('optional', 'required', 'repeated') or kind == 'oneof' and token != ';':
                    label = token if kind != 'oneof' else 'optional'
                    typ = tokens[pos] if kind != 'oneof' else token
                    if kind != 'oneof': pos += 1
                    name = tokens[pos]; pos += 1
                    assert tokens[pos] == '='; pos += 1
                    number = int(tokens[pos]); pos += 1
                    field = owner.field.add(name=name, number=number,
                        label={'optional': 1, 'required': 2, 'repeated': 3}[label])
                    if oneof is not None: field.oneof_index = oneof
                    if typ in scalar: field.type = scalar[typ]
                    else: unresolved.append((field, scope, typ))
                    while tokens[pos] != ';':
                        if tokens[pos] == 'default': field.default_value = tokens[pos+2].strip('"')
                        pos += 1
                    pos += 1
                elif kind == 'enum' and token != ';':
                    name = token
                    assert tokens[pos] == '='; pos += 1
                    owner.value.add(name=name, number=int(tokens[pos])); pos += 1
                    while tokens[pos] != ';': pos += 1
                    pos += 1
                elif token != ';':
                    # syntax/package/import declarations only.
                    while pos < len(tokens) and tokens[pos] != ';': pos += 1
                    pos += 1
        block(file, file.package)

    parse('modules/common_msgs/map_msgs/map.proto')
    for field, scope, typ in unresolved:
        candidates = [typ.lstrip('.')]
        while scope:
            candidates.insert(0, scope+'.'+typ)
            scope = scope.rpartition('.')[0]
        full = next(n for n in candidates if n in symbols)
        field.type_name = '.'+full
        field.type = 14 if symbols[full] == 'enum' else 11
    pool = descriptor_pool.DescriptorPool()
    added = set()
    def install(path):
        if path in added: return
        file = files[path]
        for dep in file.dependency: install(dep)
        pool.AddSerializedFile(file.SerializeToString())
        name = path.removesuffix('.proto').replace('/', '.')+'_pb2'
        mod = types.ModuleType(name)
        for message in file.message_type:
            setattr(mod, message.name, message_factory.GetMessageClass(pool.FindMessageTypeByName(file.package+'.'+message.name)))
        sys.modules[name] = mod
        added.add(path)
    install('modules/common_msgs/map_msgs/map.proto')
