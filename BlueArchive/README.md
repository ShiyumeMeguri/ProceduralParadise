# BlueArchive

基沃托斯（Kivotos）各学院的程序化还原。目录按 **游戏 → 学院 → 校区/房间** 组织：

```
BlueArchive/
  build.py            命令行入口（见仓库根目录 README）
  Kivotos/            全城共享：天空、太阳、光环、城市
  Millennium/         千年科学学园（Millennium Science School）
  <Academy>/          以后的学院（Trinity、Gehenna、Abydos …）沿用同样结构
```

## Kivotos（共享层）

| 模块 | 内容 |
|------|------|
| `sky.py` `build_world(cfg)` | 风格化白天天空：地平线/中段/天顶渐变（色标位置可配置），按方位角/仰角映射的积云层，可用 `clusters` 定向加云；`camera_boost` 只影响相机光线（相当于摄影里的"窗外补曝光"），不改变场景受光 |
| `sky.py` `add_sun()` | 太阳灯，方位角从正北顺时针 |
| `sky.py` `KIV.HaloRing` + `build_halo(cfg)` | 天空光环：每个光环系统是一组同心、同平面的环（圆截面管，任何角度看线宽一致），支持断弧、点线环、节点标记；系统用世界坐标（中心 + 法线）描述 |
| `city.py` `KIV.CityBlocks` | 街区网格城市：噪声聚簇高度、离校区越远越低/越高可调、校区周围留空 |
| `city.py` `KIV.Tower` `KIV.Arena` | 地标建筑：方塔/圆塔（退台顶、可选天线）、环带体育馆 |
| `city.py` `facade_material()` | 窗格立面材质（按楼随机色偏、距离雾化） |

## 学院包的约定

每个学院是一个 Python 包：

```
<Academy>/
  __init__.py         读取 Academy.json → ACADEMY / PALETTE / MOD / LEVELS / CW
  Academy.json        设计系统：模数、层高、幕墙规格、室内规格、色板
  Kit/                GN 资产（@asset 注册，名字前缀如 "MIL."）+ 材质库
  Campus/             campus.json（塔楼、地标、城市、光环）+ 塔楼生成器 + room_matrix()
  rooms.py            RoomBuilder：把 room.json 装配成房间
  Rooms/<Room>/
    room.json         房间数据（房间坐标系：原点 = 玻璃内表面线 × 前墙，+X 向室内，+Y 沿立面）
    shots/<Shot>.json 镜头：相机解算、天空、太阳、外观、自由机位 views
    Reference/        参考原画（只用于标定与对比）
    Renders/          渲染结果
```

新增房间：在 `Rooms/` 下建文件夹写 `room.json`（`placement` 指定所在塔楼、楼层、立面与偏移），
不需要改任何代码。新增学院：复制 `Millennium/` 的包结构，写自己的 `Academy.json` 与 Kit。
`build.py` 通过房间路径的第一段（学院名）自动加载对应的包。
