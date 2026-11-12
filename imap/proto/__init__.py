"""Self-contained Apollo map protobufs from the bundled FileDescriptorSet.

An isolated pool avoids conflicting with an unrelated installed `modules` package
or a different Apollo schema version. No generated Python package is required.
"""
from pathlib import Path
import sys
from types import ModuleType

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def _load():
    snapshot = descriptor_pb2.FileDescriptorSet.FromString(
        Path(__file__).with_name('map.desc').read_bytes())
    files = {file.name: file for file in snapshot.file}
    pool = descriptor_pool.DescriptorPool()
    loaded = set()

    def install(name):
        if name in loaded:
            return
        file = files[name]
        for dependency in file.dependency:
            install(dependency)
        pool.AddSerializedFile(file.SerializeToString())
        module_name = Path(name).stem + '_pb2'
        module = ModuleType(__name__ + '.' + module_name)
        module.DESCRIPTOR = pool.FindFileByName(name)
        for message in file.message_type:
            descriptor = pool.FindMessageTypeByName(file.package + '.' + message.name)
            if hasattr(message_factory, 'GetMessageClass'):
                cls = message_factory.GetMessageClass(descriptor)
            else:
                cls = message_factory.MessageFactory(pool).GetPrototype(descriptor)
            setattr(module, message.name, cls)
        globals()[module_name] = module
        sys.modules[module.__name__] = module
        loaded.add(name)

    install('modules/common_msgs/map_msgs/map.proto')


_load()
