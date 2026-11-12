# apollo_map
Map use to carla and Apollo simulation

## Maps
The map is extracted from carla `Release 0.9.14`, and then convert to Apollo map. The list of supported maps is as follows.

| Name   | Status             | Remark |
|--------|--------------------|--------|
| town01 | :heavy_check_mark: |        |
| town02 | :heavy_check_mark: |        |
| town03 | :x:                |        |
| town04 | :heavy_check_mark: |        |
| town05 | :heavy_check_mark: |        |
| town06 | :x:                |        |
| town07 | :heavy_check_mark: |        |
| town10 | :heavy_check_mark: |        |
| town11 | :x:                |        |
| town12 | :x:                |        |

## 使用本地 imap 源码

转换器源码现维护在 `imap/`，导入自工作区 `data/imap_box_0_1_10`。
原始源码目录保留，版权及 Apache-2.0 声明保留，来源与适配说明见
[imap/UPSTREAM.md](imap/UPSTREAM.md)。后续完善转换逻辑可直接修改该目录。
转换脚本默认调用本仓库 `imap.sh`，不再依赖 pip 安装的 `imap_box` 或 PATH 上的 `imap`。

在 Apollo 开发容器中加载环境，并安装转换依赖：

```bash
source /apollo/cyber/setup.bash  # 按实际容器路径调整
python3 -m pip install -r modules/map/apollo_map/requirements.txt
./modules/map/build_map.sh
```

imap 随附当前 Apollo 地图协议的 descriptor（见 [imap/proto](imap/proto/README.md)），
转换只需要 `protobuf` Python 库，不依赖 `modules.common_msgs` 或编译生成的 `*_pb2.py`。
`IMAP_PYTHON` 可指定容器或虚拟环境的 Python；安装依赖时使用同一个解释器。
完整流程的 C++ 后处理程序仍需要在 Apollo 环境中构建和运行。

```bash
# 在任意目录调用本地转换器（只转换 base_map）
/path/to/apollo/modules/map/apollo_map/imap.sh -f -i road.xodr -o /tmp/base_map.bin

# 完整转换流程，默认输出到 modules/map/data/<地图名>
cd modules/map/apollo_map
./gen_apollo_map_from_input.sh ./opendrive/straight_map straight.xodr straight

# 批量转换已存在的 Town 地图；可附加输出根目录
bash gen_apollo_map_from_town_index.sh
```

生成顺序：本地 imap 将标准 OpenDRIVE 转为 `base_map.bin/base_map.txt`，
`road_width_sample_generator` 后处理补齐 `left_road_sample/right_road_sample`，
然后生成 `sim_map` 和 `routing_map`。道路宽度后处理仅合并同向相邻的
`CITY_DRIVING` 车道，不计入对向车道或路肩。Town 批处理也使用相同流程，
现在默认直接生成完整地图到 `modules/map/data/townXX`，不再输出中间目录 `apollo/townXX`。

环境覆盖：

| 变量 | 用途 |
| --- | --- |
| `IMAP_BIN` | 显式改用其他转换器可执行文件（默认使用本地源码） |
| `IMAP_PYTHON` | 本地源码使用的 Python，默认 `python3` |
| `STOP_LINE_OFFSET` | 本地 imap 回退停止线距 signal.s 的上游距离（米），默认 1 |
| `ROAD_WIDTH_SAMPLE_GENERATOR_BIN` | 道路宽度后处理程序 |
| `SIM_MAP_GENERATOR_BIN` / `TOPO_CREATOR_BIN` | Apollo 地图生成程序 |
| `ROUTING_CONF` | routing 配置文件 |

命令行转换不加载 matplotlib、不创建窗口；需要交互可视化时额外安装
`matplotlib`，使用 `./imap.sh -m base_map.bin` 或 `./imap.sh -m road.xodr`。

交通灯转换行为详见 [SIGNAL_CONVERSION_CN.md](SIGNAL_CONVERSION_CN.md)。已按交通灯所在
laneSection、orientation 和所有 validity 范围生成关联，支持 signalReference 复用灯体，
生成灯体边界、中心位置和 lane/signal overlap。通过交通灯内的
`reference elementType="object" elementId="停止线ID" type="stopline"` 读取编辑器绑定的停止线，
按停止线自身位置和轮廓生成全部 `Signal.stop_line`；移动灯体不改变绑定停止线，绑定目标错误时报错。
没有绑定时先匹配附近上游停止线，缺失时在
signal.s 上游生成停止线；上游距离可设置 `STOP_LINE_OFFSET=2.5`，或直接向 imap 传入
`--stop-line-offset 2.5`。高程默认保留。

转换保留原始 XODR 坐标及 geoReference，与当前 CARLA 桥接的 `(x, -y, z)` 映射配套，
不会把本地坐标冒充 UTM。非零 header offset、LHT 和非标准车道方向目前会明确报错，
需要进一步实现统一坐标/车道转换后才能支持。道路宽度继续由 Apollo 后处理负责。

验证本地集成（无需安装 imap_box）：

```bash
python3 -m unittest discover -s modules/map/apollo_map/tests -v
```
