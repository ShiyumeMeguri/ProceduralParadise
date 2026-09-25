# Millennium Science School（千年科学学园）

学院包：设计系统 + 模块化 GN 资产库 + 校区总图 + 房间。目标是**整座学院**都用同一套数据与资产
搭出来；本次完成的社团活动室就是这套系统的第一个房间，它放在校区里真实塔楼的真实楼层上。

## 设计系统（`Academy.json`）

| 项 | 数值 | 说明 |
|----|------|------|
| 规划模数 | 0.3 m | 所有建筑尺寸对齐 |
| 地砖 | 1.2 m | 大理石地砖 |
| 幕墙模数 | 1.5 m | 立柱间距；与地砖每 6.0 m（结构跨）重合 |
| 层高 | 5.4 m | 吊顶基准 3.96 m，灯槽 4.2 m |
| 幕墙立柱 | 50 × 60 mm（外盖 30 mm） | 细框结构玻璃幕墙，按原画的线宽反推 |
| 横档 | 窗台 0.10 / 低横档 0.56 / 气窗横档 3.42 / 窗头 3.96 m | |
| 色板 | `palette` | 墙面白、天花蓝灰、大理石蓝、椅子白/蓝、千年蓝 … 所有材质只从这里取色 |

这些数值由 `Rooms/ClubRoom` 的摄影测量结果反推并取整到模数（见该房间 README）。

## 资产库（`Kit/`，全部为几何节点资产，可在 Blender 里直接调参）

| 资产 | 用途 |
|------|------|
| `MIL.Arch.CurtainWall` | 单元式幕墙（立柱、横档、窗台、窗头、玻璃），长度/模数/首根立柱可调 |
| `MIL.Arch.WallPanel` `MIL.Arch.Column` `MIL.Arch.FloorSlab` | 隔墙（含开洞）、柱/壁柱/收口型材、楼板 |
| `MIL.Arch.CeilingSystem` | 周边跌级吊顶 + 主吊顶 + 灯槽（coffer），含收边条 |
| `MIL.Arch.GlassDoor` | 千年风格切角门框的玻璃双开门 |
| `MIL.Fix.LinearPendant` | 吊装线性 LED 灯（配 Cycles 面光源做实际照明） |
| `MIL.Fix.HoloSign` + `MIL.Emblem` `MIL.Wordmark` | 倒梯形全息标牌、校徽（按原画轮廓矢量化）、"MILLENNIUM" 字标（笔画字体） |
| `MIL.Furn.Desk` | 实验/研讨桌单元（宽度参数化：房间里有 0.88 m 与 0.72 m 两种） |
| `MIL.Furn.Chair` = `ChairShell` + `SledBase` + `Cushion` | 一体注塑椅壳（带把手镂空）、弓形钢管底座、可叠放坐垫 |
| `MIL.Furn.Laptop` `MIL.Furn.PenCup` `MIL.Furn.BookRow` | 桌面道具 |
| `MIL.Furn.WingShelf` | 带悬挑梯形托板的展示书架 |
| `MIL.Campus.Tower` | 校区塔楼：每层每个立面都是 `MIL.Arch.CurtainWall` 实例（或竖向鳍片立面），含楼板、核心筒、屋顶 |

材质库 `Kit/materials.py`（`MIL.*`）：全部程序化，无贴图。大理石（1.2 m 砖缝、每块砖独立纹理偏移、
可调光泽/纹理尺度）、天花金属板（1.2 × 1.5 m 分缝）、薄玻璃（只在正面反射，避免出射面全反射变暗）、
全息面板、LED 等。镜头文件可以通过 `materials` 覆盖少数外观参数（如大理石光泽）。

## 校区（`Campus/`）

`campus.json` 用世界坐标（+X 东，+Y 北，米）描述：

* `towers`：千年塔楼（MIL-A 主教学楼 48 × 48 m / 36 层，MIL-B/C 研究塔，MIL-D/E …），
  `style` = `grid`（幕墙网格）或 `stripe`（竖向白色鳍片）。
* `hero_buildings`：从活动室窗户看得到的地标楼（退台玻璃塔、白色塔、玻璃裙楼、环形体育馆）。
* `city`：`KIV.CityBlocks` 参数。
* `halo`：天空光环系统（世界坐标中心、平面法线、各环半径/线宽/断弧/点线/节点）。

`room_matrix(campus, placement)` 把房间坐标系放到指定塔楼、楼层、立面、沿立面的偏移处；
房间放进塔楼时不再生成自己的幕墙，窗框就是塔楼立面本身；房间只补上隔墙与玻璃相交处的收口型材。

## 房间

| 房间 | 位置 | 说明 |
|------|------|------|
| [`Rooms/ClubRoom`](Rooms/ClubRoom/README.md) | MIL-A 24 层西立面 | 社团活动室，还原 `BG_Milleniumclub` |
