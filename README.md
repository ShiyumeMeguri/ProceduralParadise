# ProceduralParadise

用 **Blender 几何节点（Geometry Nodes）+ Python/CLI** 以程序化、模块化的方式还原游戏世界。
所有几何体都由 GN 资产生成，所有布局、尺寸、配色、镜头都写在 JSON 数据里；场景可以在命令行
一键重建、渲染，也可以存成 `.blend` 在 Blender 里自由换机位。

当前内容：**Blue Archive / 千年科学学园（Millennium）社团活动室**（`BG_Milleniumclub`），
包括窗外的千年校区塔楼、基沃托斯城市与天空光环。

![render vs reference](BlueArchive/Millennium/Rooms/ClubRoom/Renders/BG_Milleniumclub_compare.png)

## 快速开始（本地 Blender）

需要 Blender 4.4 以上（视频合成用到 4.4 起的序列编辑器接口），最近一次在 **Blender 5.3** 上验证。
不需要安装任何额外的 Python 包。

**在 Blender 界面里：**

1. 打开 Blender → 切到 **Scripting** 工作区；
2. 文本编辑器 **Text → Open**，选择仓库里的 `BlueArchive/build.py`（要打开文件本身，不要复制粘贴代码）；
3. 点 **Run Script**（▶）。约十几秒后整个场景就构建好了：社团活动室、窗外校区、光环、原画机位
   `CAM_BG_Milleniumclub` 和配布视频机位 `CAM_Showcase`。场景会自动另存为

   `Build/Millennium/ClubRoom/ClubRoom.blend`（`Build/` 在 `.gitignore` 里，不会进仓库）；
4. **Ctrl+F12** 逐帧渲染配布视频（1920×1080，30 fps，28 秒）的 PNG 序列到
   `Build/Millennium/ClubRoom/video/Showcase/<输入标识>/`。随时可以停，再按 Ctrl+F12 从断点接着渲，
   已经渲好的帧不会重渲；全部渲完后切到场景 **Showcase Video** 再按 Ctrl+F12，合成
   `video/Showcase.mp4`。单帧预览按 F12；想渲染原画机位，把 `CAM_BG_Milleniumclub` 设为活动相机、分辨率改为 1280×900。

`<输入标识>` 由 Blender 版本、影响画面的参数和本次构建读入的全部代码与 JSON 算出：改了场景再构建，
新帧进新文件夹，旧帧原样保留、绝不混进新视频；改回原样会接着用原来那批帧。

若本机有显卡且 Cycles 还没配置计算设备，脚本会自动启用 GPU（OptiX / CUDA / HIP / Metal / oneAPI），
降噪也放在显卡上做。长片建议用下面的命令行渲染，比在界面里按 Ctrl+F12 快。

**命令行：**

```bash
# 默认：构建并保存 Build/Millennium/ClubRoom/ClubRoom.blend
blender -b -P BlueArchive/build.py

# 构建、渲染还缺的帧并合成配布视频 Build/Millennium/ClubRoom/video/Showcase.mp4（可随时中断，重跑接着渲）
blender -b -P BlueArchive/build.py -- --render-animation

# 快速试看：1/4 分辨率、12 采样、不画描边
blender -b -P BlueArchive/build.py -- --render-animation --scale 0.25 --samples 12 --no-lines

# 渲染原画机位 / 自由机位的单帧
blender -b -P BlueArchive/build.py -- --render still.png
blender -b -P BlueArchive/build.py -- --view reverse --render reverse.png
```

也可以用 PyPI 的 `bpy` 模块代替 Blender：`python BlueArchive/build.py [同样的参数]`。
全部参数见 `BlueArchive/build.py` 顶部说明。无显示器的 Linux 上渲染描边（Freestyle）需要 EGL：
安装 Mesa EGL 并设置 `EGL_PLATFORM=surfaceless`。

## 目录结构

```
Core/                     与游戏无关的通用框架
  nodes.py                节点树 DSL（运算符重载、版本兼容的节点解析）
  gn.py                   几何节点构建器 + 资产注册表（@asset）
  scene.py camera.py      场景/集合/GN 对象；摄影测量相机（焦距、主点偏移、两点透视）
  shaders.py render.py    程序化材质；Cycles、合成器外观（曝光、辉光、调色、Freestyle 描边）、视频输出
  anim.py                 相机动画：关键帧 + 平滑样条手柄，可在 Graph Editor 里继续调
  grade.py compare.py     调色拟合（直方图/色卡/回归）；与参考图的叠线、区域色差、SSIM 对比
BlueArchive/
  build.py                命令行入口：学院 → 校区 → 房间 → 镜头
  Kivotos/                整个基沃托斯共享：天空、太阳、光环、城市生成器
  Millennium/             千年科学学园
    Academy.json          学院设计系统（模数、层高、幕墙、色板）
    Kit/                  模块化 GN 资产库（建筑、家具、灯具、标识、材质）
    Campus/               校区总图 + 塔楼生成器（房间嵌在真实塔楼的真实立面里）
    rooms.py              由 room.json 装配房间
    Rooms/ClubRoom/       本次还原的社团活动室（room.json、镜头、配布视频动画、参考图、渲染结果）
Build/                    构建输出（.blend、视频），git 忽略
```

## 设计原则

* **没有"硬编码"几何**：每件东西都是带参数的 GN 资产，房间/校区只是数据。换一个房间只需要写一个
  新的 `room.json`，新学院复制 `Millennium/` 的结构并写自己的 `Academy.json`。
* **统一设计系统**：0.3 m 规划模数、1.2 m 地砖、1.5 m 幕墙模数、6.0 m 结构跨、5.4 m 层高。
  所有房间与塔楼共享这些数值，所以教室放进校区时立面、楼板、窗格天然对齐。
* **房间在塔楼里**：社团活动室位于 MIL-A 塔 24 层西立面；从房间里看出去的窗框就是塔楼本身的幕墙，
  窗外的楼、城市、光环都是世界坐标里的真实几何体，任何机位看到的都是同一个世界。
* **不用投影、不贴原图**：参考图只用于标定相机、测量尺寸和拟合颜色；渲染时从不采样参考图。
* **可验证**：`Core/compare.py` 生成几何叠线图（模型轮廓 vs 参考图边缘）、区域色差表和 SSIM，
  每次修改都用数字说话。
