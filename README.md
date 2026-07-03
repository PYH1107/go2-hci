# Go2 语音控制 - 快速开始

## 系统概述

**Input**: 你的声音 → **Output**: Go2 执行动作

```
声音 → Whisper → 文本 → 意图解析 → SDK/Nav2 → 动作
```

## ref.
- [[Unitree Go2] Access to Speaker and Microphone](https://forum.mybotshop.de/t/unitree-go2-access-to-speaker-and-microphone/1036)
- [Go2 机器狗实验指导书：第 16 章 语音交互系统](https://ztl3106742440-hub.github.io/go2-tutorial/05-interaction/16-voice/)
- [ROS2理论与实践_宇树机器人Go2开发指南](https://www.bilibili.com/video/BV1vv5YzBEQH?spm_id_from=333.788.videopod.episodes&vd_source=cb1e076f51948a7c55b8e7d36bc8063d)

> [!WARNING]
> 上述资料表示 go2 不支持语音 topic，而得采用外接的麦克风设备

---

## 语音指令列表


### 原地动作（SDK 直接控制）

### 导览点（Nav2）
| 指令 | action_id |
|------|----------|
| 去院史馆 / 院史馆 | `nav_history_museum` |
| 去资料室 / 资料室 | `nav_archive_room` |
| 去保密学院 / 保密学院 | `nav_school_of_classified` |
| 去人机交互实验室 / 人机交互 | `nav_hci_lab` |

---

## Nav2 导航设置

### 1. 资料格式：poses.yaml

导览点姿态定义在 `config/poses.yaml`：

```yaml
# 格式：action_id (必须与 COMMAND_MAP 中的对应)
nav_history_museum:
  frame: "map"                    # 参考坐标系
  position:
    x: 5.2                       # X 坐标（公尺）
    y: 3.1                       # Y 坐标（公尺）
    z: 0.0                       # Z 坐标（公尺）
  orientation:
    x: 0.0                       # Quaternion X
    y: 0.0                       # Quaternion Y
    z: 0.707                     # Quaternion Z
    w: 0.707                     # Quaternion W

nav_archive_room:
  frame: "map"
  position:
    x: -2.1
    y: 1.5
    z: 0.0
  orientation:
    x: 0.0
    y: 0.0
    z: 1.0
    w: 0.0
```

**坐标获取方式**：
- 使用 `ros2 run nav2_simple_commander basic_navigator` 或
- 使用 RViz2 的「2D Pose Estimate」工具记录目标位置
- 或从地图文件直接读取已知坐标

---

### 2. 语音关键字映射

导览点的语音关键字定义在 `voice_cmd.py` 的 `COMMAND_MAP`：

```python
# 在 voice_cmd.py 中定义
COMMAND_MAP = [
    # ... 其他指令 ...
    (["去院史馆", "院史馆"], "nav_history_museum", "去院史馆"),
    (["去资料室", "资料室"], "nav_archive_room", "去资料室"),
    # ...
]
```

---

### 3. Nav2 接收方式

语音系统发布 `geometry_msgs/PoseStamped` 到 `/goal_pose` topic：

```bash
# 监听导航目标
ros2 topic echo /goal_pose
```

**Nav2 需要配置**：创建一个简单的 goal subscriber 或使用 Nav2 的 Navigation2 API。

---

## 添加新的导览点

### 步骤 1：在 poses.yaml 添加姿态

```yaml
nav_new_location:
  frame: "map"
  position:
    x: 10.0
    y: 5.0
    z: 0.0
  orientation:
    x: 0.0
    y: 0.0
    z: 0.0
    w: 1.0
```

### 步骤 2：在 voice_cmd.py 添加关键字

```python
COMMAND_MAP = [
    # ...
    (["去新地点", "新地点"], "nav_new_location", "去新地点"),
]
```

### 步骤 3：重新编译

```bash
colcon build --packages-select go2_voice
source install/setup.bash
```

---

## 安装与运行

### 依赖安装

```bash
# Python 依赖
pip install faster-whisper edge-tts numpy pyyaml

# ROS2 依赖
sudo apt install ros-humble-nav2-msgs
```

### 编译

```bash
cd ~/go2-hci

# 只编译语音包（最快）
colcon build --packages-select go2_voice

# 或一次编译全部（含 base 驱动、桥接等 6 个套件）
colcon build

source install/setup.bash
```

### 运行

```bash
# 终端 1：启动语音控制
ros2 run go2_voice voice_cmd

# 终端 2：监听导航目标（可选）
ros2 topic echo /goal_pose
```

---

## 环境变量

```bash
# 网卡接口（默认 enp3s0）
export GO2_NET_IFACE="enp3s0"

# Whisper 模型（默认 small）
export GO2_WHISPER_MODEL="small"
```
---

## 文件结构

```
go2-hci/                          # colcon workspace 根目录
├── src/
│   └── go2_voice/                # 语音互动（本项目主线）
│       ├── go2_voice/
│       │   ├── voice_cmd.py      # 主程序
│       │   └── build_prompts.py  # 语音生成工具
│       ├── config/
│       │   └── poses.yaml        # 导览点姿态定义
│       ├── audio/                # 预生成语音 mp3
│       ├── launch/
│       │   └── voice.launch.py   # ROS2 启动文件
│       ├── resource/             # ament package 资源标记
│       ├── test/                 # flake8 / copyright / pep257
│       ├── package.xml
│       ├── setup.py
│       └── setup.cfg
└── README.md
```
