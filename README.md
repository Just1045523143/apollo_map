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

## Quick start
You can use the Apollo map in the following steps.

**Steps:**

1. **Clone Apollo Map Repository:**

   ```bash
   git clone apollo_map
   ```

   This will clone the Apollo map data repository into your local directory.

2. **Convert OpenDRIVE Map to Apollo Format:**

   ```bash
   sh gen_apollo_map_from_town_index.sh
   ```

   This script converts the OpenDRIVE format map into the format required by Apollo.

3. **Place Converted Map in the Correct Directory:**

   ```bash
   cp <converted_map_dir> modules/map/data/
   ```

   Replace `<converted_map_dir>` with the actual directory of the generated Apollo map file. Move this directory to the `modules/map/data/` directory.

4. **Generate Routing Map:**

   ```bash
   sh gen_dep_map_from_town_index.sh
   ```

   This step generates a routing map for path planning.

5. **Restart Dreamview:**

   ```bash
   ./scripts/bootstrap.sh restart
   ```

   If you want to visualize the map in Dreamview, restart Dreamview using this command.

**Additional Notes:**

* Ensure you have the necessary permissions to execute the scripts.
* Refer to the official Apollo project documentation for more detailed information on Apollo maps.

### my command list
首先需要安装imap
```bash
pip3 install imap_box
```

首次使用时，在 Apollo 容器内编译道路宽度后处理工具：

```bash
./modules/map/build_map.sh
```

生成顺序为：标准 OpenDRIVE 经 `imap` 转换为 `base_map.bin`，然后
`road_width_sample_generator` 补齐 Apollo 专用的
`left_road_sample/right_road_sample`，最后生成 `sim_map` 和 `routing_map`。
后处理器仅合并 `left/right_neighbor_forward_lane_id` 连通的同向
`CITY_DRIVING` 车道，不会把对向车道或路肩计入 Planning 道路宽度。


安装并编译好后直接执行：
```bash
cd modules/map/apollo_map
#                                xodr目录             xodr地图名字
./gen_apollo_map_from_input.sh ./opendrive/rong_map/ rong_map.xodr  # 在modules/map/data目录下生成完整的地图
```