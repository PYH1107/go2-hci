# Go2 語音控制 - 快速開始

## 系統概述

**Input**: 你的聲音 → **Output**: Go2 執行動作

```
聲音 → Whisper → 文本 → 意圖解析 → SDK/Nav2 → 動作
```

## ref.
	- [[Unitree Go2] Access to Speaker and Microphone](https://forum.mybotshop.de/t/unitree-go2-access-to-speaker-and-microphone/1036)
	- [Go2 机器狗实验指导书：第 16 章 语音交互系统](https://ztl3106742440-hub.github.io/go2-tutorial/05-interaction/16-voice/)
	- [ROS2理论与实践_宇树机器人Go2开发指南](https://www.bilibili.com/video/BV1vv5YzBEQH?spm_id_from=333.788.videopod.episodes&vd_source=cb1e076f51948a7c55b8e7d36bc8063d)


---

## 語音指令列表

### 喚醒詞
說「小白」進入待命狀態

### 原地動作（SDK 直接控制）
| 指令 | 動作 |
|------|------|
| 坐下 / 蹲下 | 趴下 |
| 站起 / 起來 | 站起來 |
| 前進 / 向前 | 前進 ~1.7 秒 |
| 後退 / 往後 | 後退 ~1.7 秒 |
| 左轉 / 向左 | 左轉 ~180° |
| 右轉 / 向右 | 右轉 ~180° |
| 打招呼 / 你好 | 打招呼 |
| 伸懶腰 / 伸展 | 伸懶腰 |
| 轉圈 / 轉一圈 | 原地轉圈 |
| 跳舞 | 跳舞 |
| 比心 | 比心 |
| 後空翻 | 後空翻（需二次確認） |
| 前空翻 | 前空翻（需二次確認） |
| 恢復 / 復位 | 恢復站立 |

### 導覽點（Nav2）
| 指令 | action_id |
|------|----------|
| 去院史館 / 院史館 | `nav_history_museum` |
| 去資料室 / 資料室 | `nav_archive_room` |
| 去保密學院 / 保密學院 | `nav_school_of_classified` |
| 去人機交互實驗室 / 人機交互 | `nav_hci_lab` |

---

## Nav2 導航設置

### 1. 資料格式：poses.yaml

導覽點姿態定義在 `config/poses.yaml`：

```yaml
# 格式：action_id (必須與 COMMAND_MAP 中的對應)
nav_history_museum:
  frame: "map"                    # 參考坐標系
  position:
    x: 5.2                       # X 坐標（公尺）
    y: 3.1                       # Y 坐標（公尺）
    z: 0.0                       # Z 坐標（公尺）
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

**坐標獲取方式**：
- 使用 `ros2 run nav2_simple_commander basic_navigator` 或
- 使用 RViz2 的「2D Pose Estimate」工具記錄目標位置
- 或從地圖文件直接讀取已知坐標

---

### 2. 語音關鍵字映射

導覽點的語音關鍵字定義在 `voice_cmd.py` 的 `COMMAND_MAP`：

```python
# 在 voice_cmd.py 中定義
COMMAND_MAP = [
    # ... 其他指令 ...
    (["去院史館", "院史館"], "nav_history_museum", "去院史館"),
    (["去資料室", "資料室"], "nav_archive_room", "去資料室"),
    # ...
]
```

---

### 3. Nav2 接收方式

語音系統發布 `geometry_msgs/PoseStamped` 到 `/goal_pose` topic：

```bash
# 監聽導航目標
ros2 topic echo /goal_pose
```

**Nav2 需要配置**：創建一個簡單的 goal subscriber 或使用 Nav2 的 Navigation2 API。

---

## 添加新的導覽點

### 步驟 1：在 poses.yaml 添加姿態

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

### 步驟 2：在 voice_cmd.py 添加關鍵字

```python
COMMAND_MAP = [
    # ...
    (["去新地點", "新地點"], "nav_new_location", "去新地點"),
]
```

### 步驟 3：重新編譯

```bash
colcon build --packages-select go2_voice
source install/setup.bash
```

---

## 安裝與運行

### 依賴安裝

```bash
# Python 依賴
pip install faster-whisper edge-tts numpy pyyaml

# ROS2 依賴
sudo apt install ros-humble-nav2-msgs
```

### 編譯

```bash
cd ~/unitree_go2_ws
colcon build --packages-select go2_voice
source install/setup.bash
```

### 運行

```bash
# 終端 1：啟動語音控制
ros2 run go2_voice voice_cmd

# 終端 2：監聽導航目標（可選）
ros2 topic echo /goal_pose
```

---

## 環境變量

```bash
# 網卡介面（默認 enp3s0）
export GO2_NET_IFACE="enp3s0"

# Whisper 模型（默認 small）
export GO2_WHISPER_MODEL="small"
```
---

## 檔案結構

```
go2_voice/
├── go2_voice/
│   ├── voice_cmd.py       # 主程式
│   └── build_prompts.py  # 語音生成工具
├── config/
│   └── poses.yaml         # 導覽點姿態定義
├── audio/                 # 預生成語音檔案
└── launch/
    └── voice.launch.py    # ROS2 啟動檔
```
