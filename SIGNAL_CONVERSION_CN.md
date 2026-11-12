# 交通灯、停止线与坐标约定

实现位于 `imap/lib/signal_conversion.py`、`signal_geometry.py`，由 `convertor.py`
在所有道路生成后调用，确保跨道路 signalReference 能引用已有灯体和车道。

## 信号适用车道

- 按 `signal.s` 选择 laneSection；边界站号归属后一段。
- RHT 中负编号 driving 车道沿 +s，正编号 driving 车道沿 −s。
  orientation 与全部 validity 区间共同筛选，none 允许双向；不会统一关联最后一段右侧车道。
- `<signalReference>` 使用自身道路、s/orientation/validity 添加关联，不复制或移动原灯体。
- 每个 laneSection 仅取本段采样点，并插值补齐段端点。车道长度、samples 和 overlap
  使用行驶方向上的实际中心折线弧长；不直接将道路 s 写作车道局部 s。

## 停止线优先级

1. 优先使用 `<signal><reference elementType="object" elementId="..."/></signal>`
   引用的停止线。支持 `object type="roadMark" subtype="signalLines"/"stopLine"`
   或 `type="stopLine"`。其他类型对象引用不充当停止线。
2. 没有显式引用时，查找同道路上游 30 米内、方向匹配且实际与有效车道相交的最近停止线。
   这是转换器的匹配策略，复杂路口应使用显式引用避免歧义。
3. 缺失时按 `signal.s - 行驶方向 × stop_line_offset` 插值生成，默认上游 1 米。
   不再按 point[-index] 抽取道路终点。结果限制在本道路站号范围内。

显式停止线支持横向条带的 cornerLocal、cornerRoad 轮廓；没有轮廓时使用物体宽度。
从条带生成中心线，使用该线与车道中心线的交点计算 overlap 弧长。多个车道共享的
同一停止线只输出一次几何。显式停止线不横跨的车道不会生成关联，也不会另造回退线。
绑定元素先独立生成 Apollo `Signal.stop_line`，再计算车道关联；即使没有有效车道相交，
仍保留绑定停止线的几何，不会用交通灯坐标或附近未绑定的停止线替换它。
同一盏灯绑定多条停止线时全部输出；同一车道与多条线相交时，overlap 选用距灯的道路站号最近的一条。
移动交通灯只改变灯体位置；移动停止线或修改其轮廓才会改变对应停止线几何。
带 `type="stopline"`/`"stop_line"` 的对象引用必须全部解析成功；目标不存在、类型不支持、
横向宽度为零或站号超出道路范围时转换报错，不会因另有一条有效绑定而忽略错误。
任意复杂多边形、多条独立 outline、重复 repeat 物体暂未作为精确停止线几何支持。

编辑器导出的绑定格式示例（对象与灯属于同一道路）：

```xml
<object id="stop-1" type="roadMark" subtype="signalLines"
        s="40" t="-5.25" width="10.5" length="0.4" zOffset="0" hdg="0"/>
<!-- 以下 reference 位于交通灯的 signal 元素内 -->
<reference elementType="object" elementId="stop-1" type="stopline"/>
```

停止线跨 laneSection 时按明确的 lane link 寻找对应车道；缺少有效链接时报错，
不会假定段间同编号车道必然相连。

`LaneOverlapInfo.start_s/end_s` 均为停止线与中心线交点的局部弧长，表示零长度的停止位置；
`SignalOverlapInfo` 使用 SetInParent 设置空消息存在性，并填写 lane/signal 的 overlap_id。

## 灯体与朝向

灯体原点按参考线的 s/t、参考线高程与 zOffset 计算，不叠加 laneOffset。
orientation='+' 的灯面朝 −s，orientation='-' 朝 +s，叠加逆时针 hOffset；
pitch/roll 作用于灯体边界和中心位置。该定义对应
[ASAM OpenDRIVE 1.8.1 信号规则](https://publications.pages.asam.net/standards/ASAM_OpenDRIVE/ASAM_OpenDRIVE_Specification/v1.8.1/specification/14_signals/14_01_introduction.html)。

通用 OpenDRIVE 1000001/-1 只标识交通灯，不能据此推断三灯排列和箭头灯类型。
因此生成 UNKNOWN 类型及中心 subsignal，位置可供 Dreamview 放置示意灯模型；不编造灯泡布局。
Apollo Signal 没有独立 orientation 字段，方向由边界几何表达，下游应按边界解释。
暂未为其他国家灯型编码建立转换目录。

## 投影与 CARLA 桥接

当前桥接 `carla_bridge/utils/transforms.py` 将 CARLA `(x,y,z)` 映射为 Apollo `(x,-y,z)`，
未做 UTM 重投影。转换器因此保留 OpenDRIVE 原始工程坐标，并原样保留 geoReference。
去掉旧实现的投影原点平移和强制 UTM 声明。没有 geoReference 时保留本地坐标、空投影并提示。

本次没有引入整体 UTM 变换。未来若需要 UTM，必须统一变换地图所有几何与桥接的
定位、TF、障碍物、规划控制输入，不能只改地图头或只平移车道。
非零 header offset 暂时报错，避免与 CARLA 的 offset 应用约定不一致。
由于现有基础车道生成按 RHT 实现，LHT、非标准 lane direction 也暂时报错。

## 验证

`python3 -m unittest discover -s modules/map/apollo_map/tests -v`。
测试包含当前 straight.xodr、signal.s 移动、不同采样间距、反向、多 validity、跨段链接、
显式与自动匹配停止线、灯体倾角、跨路 signalReference、原始投影，以及二进制序列化往返。
无 protoc 时，测试从当前仓库 proto2 schema 构造真实 protobuf descriptor；
生产入口使用随附的 `imap/proto/map.desc`，无需 Apollo Python 包；测试比较随附协议与源码，
并用独立的消息类验证二进制兼容性。修改 map proto 后运行
`tools/update_map_descriptors.py` 更新快照（维护命令需要 protoc 或 grpcio-tools）。
