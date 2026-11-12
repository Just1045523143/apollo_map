# Apollo map schema snapshot

`map.desc` is a protobuf FileDescriptorSet containing the current repository's
`modules/common_msgs/map_msgs/map.proto` and all transitive imports (19 files).
The definitions retain their original protobuf names, field numbers, enums,
defaults and oneof semantics. They produce Apollo-compatible binary maps.

The converter loads these definitions into an isolated descriptor pool, so it
does not depend on the Python search path or an installed Apollo `_pb2` package.
Only the `protobuf` Python runtime is needed. Source schemas remain the authority.

After changing Apollo map schemas, regenerate from the Apollo repository root:

```bash
python3 modules/map/apollo_map/tools/update_map_descriptors.py
```

This maintenance command needs `protoc` or the `grpcio-tools` Python package.
Neither compiler is needed to run imap. The tests compare the snapshot with the
checked-in schemas and verify binary interoperability with separately loaded messages.
