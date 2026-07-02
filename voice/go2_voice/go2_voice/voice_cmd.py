#!/usr/bin/env python3
"""
Go2 語音控制主程式。
主線是: 待機 -> 喚醒 -> 一條指令 -> 執行動作 -> 回待機。
"""

import multiprocessing
import os
import queue
import subprocess
import threading
import time
from enum import Enum
from pathlib import Path

import numpy as np
import yaml
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_DURATION = 0.1
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)
BYTES_PER_BLOCK = BLOCK_SIZE * 2

ENERGY_THRESHOLD = 0.02
SILENCE_TIMEOUT = 0.8
MIN_SPEECH_DURATION = 0.2
MAX_SPEECH_DURATION = 10.0
ACTIVE_TIMEOUT = 30.0

NETWORK_INTERFACE = os.getenv("GO2_NET_IFACE", "enp3s0")
MODEL_PATH = os.getenv("GO2_WHISPER_MODEL", "small")
WAKE_WORDS = ["小白"]

AUDIO_DIR = Path(__file__).resolve().parents[1] / "audio"

# 嘗試從多個位置尋找 config 目錄
# 1. 開發環境：相對於模組的 src/voice/go2_voice/config/
# 2. 安裝環境：install/.../share/go2_voice/config/
def _find_config_dir() -> Path:
    """尋找 config 目錄，支援開發和安裝環境。"""
    # 嘗試相對於模組的路徑（開發環境）
    module_dir = Path(__file__).resolve().parents[1]
    relative_config = module_dir / "config"
    if relative_config.exists():
        return relative_config

    # 嘗試從 ament share 路徑（安裝環境）
    try:
        import ament_index_python
        share_path = Path(ament_index_python.get_package_share_directory('go2_voice'))
        share_config = share_path / "config"
        if share_config.exists():
            return share_config
    except Exception:
        pass

    # 回退到相對路徑（可能不存在）
    return relative_config

CONFIG_DIR = _find_config_dir()
POSES_FILE = CONFIG_DIR / "poses.yaml"
audio_queue: "queue.Queue[np.ndarray]" = queue.Queue()

_parecord_proc = None
_recording = False


class State(Enum):
    SLEEPING = "sleeping"
    ACTIVE = "active"


def load_poses() -> dict[str, dict]:
    """
    從 poses.yaml 載入導覽點姿態資訊。
    返回格式: {action_id: {frame, position, orientation}}
    """
    if not POSES_FILE.exists():
        return {}

    try:
        with open(POSES_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as exc:
        print(f"[警告] 載入姿態檔案失敗: {exc}")
        return {}


def _find_usb_source() -> str | None:
    """從 PulseAudio/PipeWire 找 USB 麥克風 source 名稱。"""
    try:
        output = subprocess.check_output(
            ["pactl", "list", "sources", "short"],
            stderr=subprocess.DEVNULL,
        ).decode()
    except Exception:
        return None

    for line in output.strip().splitlines():
        if "usb" in line.lower() and "monitor" not in line.lower():
            return line.split()[1]
    return None


def _parecord_reader() -> None:
    """後台執行緒: 不斷把 parecord 的 PCM 資料讀出來，切成小塊塞進佇列。"""
    global _parecord_proc
    buffer = b""

    while _recording and _parecord_proc and _parecord_proc.poll() is None:
        data = _parecord_proc.stdout.read(BYTES_PER_BLOCK)
        if not data:
            break

        buffer += data
        while len(buffer) >= BYTES_PER_BLOCK:
            block = buffer[:BYTES_PER_BLOCK]
            buffer = buffer[BYTES_PER_BLOCK:]
            samples = np.frombuffer(block, dtype=np.int16).astype(np.float32) / 32768.0
            audio_queue.put(samples)


def start_recording() -> None:
    """啟動 parecord 子程式和讀取執行緒。"""
    global _parecord_proc, _recording

    cmd = [
        "parecord",
        f"--rate={SAMPLE_RATE}",
        f"--channels={CHANNELS}",
        "--format=s16le",
        "--raw",
    ]

    source_name = _find_usb_source()
    if source_name:
        cmd.append(f"--device={source_name}")

    _parecord_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    _recording = True
    threading.Thread(target=_parecord_reader, daemon=True).start()


def stop_recording() -> None:
    """退出時記得把錄音子程式收乾淨。"""
    global _recording, _parecord_proc

    _recording = False
    if _parecord_proc:
        _parecord_proc.terminate()
        _parecord_proc.wait(timeout=3)
        _parecord_proc = None


def record_speech(timeout: float = 0.0) -> np.ndarray | None:
    """
    等待一段語音。
    timeout=0 表示無限等待;
    返回 None 表示超時或沒檢測到有效語音。
    """
    speech_chunks: list[np.ndarray] = []
    is_speaking = False
    speech_start = 0.0
    silence_start = 0.0
    wait_start = time.time()

    while True:
        try:
            chunk = audio_queue.get(timeout=0.5)
        except queue.Empty:
            if timeout > 0 and not is_speaking and time.time() - wait_start > timeout:
                return None
            continue

        energy = float(np.sqrt(np.mean(chunk ** 2)))

        if not is_speaking:
            if timeout > 0 and time.time() - wait_start > timeout:
                return None
            if energy > ENERGY_THRESHOLD:
                is_speaking = True
                speech_start = time.time()
                speech_chunks = [chunk]
        else:
            speech_chunks.append(chunk)

            if energy < ENERGY_THRESHOLD:
                if silence_start == 0:
                    silence_start = time.time()
                elif time.time() - silence_start > SILENCE_TIMEOUT:
                    duration = time.time() - speech_start
                    if duration < MIN_SPEECH_DURATION:
                        speech_chunks.clear()
                        is_speaking = False
                        silence_start = 0.0
                        continue
                    return np.concatenate(speech_chunks)
            else:
                silence_start = 0.0

            if time.time() - speech_start > MAX_SPEECH_DURATION:
                return np.concatenate(speech_chunks)


def transcribe(model: WhisperModel, audio_data: np.ndarray) -> str:
    """把一段音頻轉成中文文本。"""
    segments, _ = model.transcribe(
        audio_data,
        language="zh",
        beam_size=3,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
        },
        initial_prompt=(
            "小白；坐下；站起；前進；後退；左轉；右轉；"
            "打招呼；伸懶腰；轉圈；跳舞；比心；前空翻；後空翻；"
            "停止；確認；取消；"
            "去院史館；院史館；去資料室；資料室；去保密學院；國家保密學院；去人機交互實驗室；人機交互"
        ),
    )
    return "".join(segment.text for segment in segments).strip()


CHAR_NORMALIZE = {
    "確": "确", "認": "认", "後": "后", "轉": "转", "動": "动",
}

WORD_NORMALIZE = {
    "小百": "小白",
    "拜拜": "小白",
    "做轉": "左轉",
    "有轉": "右轉",
    "筆心": "比心",
    "後翻": "後空翻",
    "前翻": "前空翻",
    # 導覽點誤識別修正
    "院史馆": "院史館",
    "资料室": "資料室",
    "保密学院": "國家保密學院",
}


def normalize_asr(text: str) -> str:
    """繁簡修正 + 已知誤識別修正。"""
    text = "".join(CHAR_NORMALIZE.get(ch, ch) for ch in text)
    for wrong, right in sorted(WORD_NORMALIZE.items(), key=lambda item: -len(item[0])):
        text = text.replace(wrong, right)
    return text


STOP_KEYWORDS = ["停", "停下", "停止", "暫停", "取消", "夠了", "結束"]

DANGEROUS_ACTIONS = {"back_flip", "front_flip", "combo_1"}

COMMAND_MAP = [
    (["坐下", "蹲下", "趴下"], "stand_down", "趴下"),
    (["站起", "起來", "起立", "站立"], "stand_up", "站起來"),
    (["前進", "向前", "往前"], "move_forward", "前進"),
    (["後退", "往後", "退後"], "move_back", "後退"),
    (["左轉", "向左", "往左"], "turn_left", "左轉"),
    (["右轉", "向右", "往右"], "turn_right", "右轉"),
    (["打招呼", "握手", "你好"], "hello", "打招呼"),
    (["伸懶腰", "伸展"], "stretch", "伸懶腰"),
    (["轉圈", "轉一圈"], "spin", "原地轉圈"),
    (["跳舞"], "dance1", "跳舞"),
    (["比心"], "heart", "比心"),
    (["後空翻"], "back_flip", "後空翻"),
    (["前空翻"], "front_flip", "前空翻"),
    (["恢復", "復位"], "recovery", "恢復站立"),
    # 導覽點指令（需要配合 Nav2 導航系統）
    (["去院史館", "去院史馆", "去歷史館", "院史館", "院史馆"], "nav_history_museum", "去院史館"),
    (["去資料室", "去资料室", "去檔案室", "資料室", "资料室"], "nav_archive_room", "去資料室"),
    (["去保密學院", "去國家保密學院", "去保密学院", "保密學院", "保密学院"], "nav_school_of_classified", "去國家保密學院"),
    (["去人機交互實驗室", "去交互實驗室", "去互動實驗室", "人機交互"], "nav_hci_lab", "去人機交互實驗室"),
]


def check_wake_word(text: str) -> bool:
    return any(word in text for word in WAKE_WORDS)


def check_stop(text: str) -> bool:
    return any(word in text for word in STOP_KEYWORDS)


def parse_intent(text: str) -> tuple[str, str] | None:
    text = text.strip().lower()
    for keywords, action_id, desc in COMMAND_MAP:
        if any(keyword in text for keyword in keywords):
            return action_id, desc
    return None


def _sdk_worker(cmd_queue: multiprocessing.Queue, result_queue: multiprocessing.Queue, network_interface: str) -> None:
    """動作執行子程式: 只負責 SDK 初始化和動作調用。"""
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.go2.sport.sport_client import SportClient

    # 初始化 ROS2 用於導航
    import rclpy
    from geometry_msgs.msg import PoseStamped

    rclpy.init()
    nav_node = rclpy.create_node("voice_nav_publisher")
    goal_pub = nav_node.create_publisher(PoseStamped, "/goal_pose", 10)

    ChannelFactoryInitialize(0, network_interface)

    client = SportClient()
    client.SetTimeout(10.0)
    client.Init()

    # 載入姿態資訊
    poses = load_poses()

    result_queue.put("READY")

    while True:
        action_id = cmd_queue.get()
        if action_id == "__EXIT__":
            break

        ret = None
        try:
            if action_id == "stand_down":
                ret = client.StandDown()
            elif action_id == "stand_up":
                ret = client.StandUp()
            elif action_id == "recovery":
                ret = client.RecoveryStand()
            elif action_id == "move_forward":
                t0 = time.time()
                while time.time() - t0 < 1.7:
                    client.Move(0.3, 0.0, 0.0)
                    time.sleep(0.05)
                client.StopMove()
                ret = 0
            elif action_id == "move_back":
                t0 = time.time()
                while time.time() - t0 < 1.7:
                    client.Move(-0.3, 0.0, 0.0)
                    time.sleep(0.05)
                client.StopMove()
                ret = 0
            elif action_id == "turn_left":
                t0 = time.time()
                while time.time() - t0 < 3.14:
                    client.Move(0.0, 0.0, 0.5)
                    time.sleep(0.05)
                client.StopMove()
                ret = 0
            elif action_id == "turn_right":
                t0 = time.time()
                while time.time() - t0 < 3.14:
                    client.Move(0.0, 0.0, -0.5)
                    time.sleep(0.05)
                client.StopMove()
                ret = 0
            elif action_id == "hello":
                ret = client.Hello()
            elif action_id == "stretch":
                ret = client.Stretch()
            elif action_id == "spin":
                t0 = time.time()
                while time.time() - t0 < 4.19:
                    client.Move(0.0, 0.0, 1.5)
                    time.sleep(0.05)
                client.StopMove()
                ret = 0
            elif action_id == "dance1":
                ret = client.Dance1()
            elif action_id == "heart":
                ret = client.Heart()
            elif action_id == "back_flip":
                ret = client.BackFlip()
            elif action_id == "front_flip":
                ret = client.FrontFlip()
            elif action_id == "emergency_stop":
                client.StopMove()
                client.RecoveryStand()
                ret = 0
            elif action_id.startswith("nav_"):
                # 導航指令: 從姿態資訊發布目標姿態
                if action_id in poses:
                    pose_data = poses[action_id]
                    # 驗證姿態資料結構
                    required_keys = ["position", "orientation"]
                    position_keys = ["x", "y", "z"]
                    orientation_keys = ["x", "y", "z", "w"]

                    valid = True
                    for key in required_keys:
                        if key not in pose_data:
                            valid = False
                            break
                    if valid:
                        for key in position_keys:
                            if key not in pose_data["position"]:
                                valid = False
                                break
                    if valid:
                        for key in orientation_keys:
                            if key not in pose_data["orientation"]:
                                valid = False
                                break

                    if not valid:
                        ret = -1
                    else:
                        msg = PoseStamped()
                        msg.header.stamp = nav_node.get_clock().now().to_msg()
                        msg.header.frame_id = pose_data.get("frame", "map")
                        msg.pose.position.x = pose_data["position"]["x"]
                        msg.pose.position.y = pose_data["position"]["y"]
                        msg.pose.position.z = pose_data["position"]["z"]
                        msg.pose.orientation.x = pose_data["orientation"]["x"]
                        msg.pose.orientation.y = pose_data["orientation"]["y"]
                        msg.pose.orientation.z = pose_data["orientation"]["z"]
                        msg.pose.orientation.w = pose_data["orientation"]["w"]
                        goal_pub.publish(msg)
                        # 等待訊息發布完成
                        rclpy.spin_once(nav_node, timeout_sec=0.1)
                        ret = 0
                else:
                    ret = -1
            else:
                ret = -1

            result_queue.put("OK" if ret in (None, 0) else f"FAIL:{ret}")
        except Exception as exc:
            result_queue.put(f"ERROR:{exc}")

    # 清理 ROS2 資源
    nav_node.destroy_node()
    rclpy.shutdown()


class Go2Controller:
    def __init__(self) -> None:
        self._cmd_q: multiprocessing.Queue = multiprocessing.Queue()
        self._res_q: multiprocessing.Queue = multiprocessing.Queue()
        self._proc: multiprocessing.Process | None = None
        self._spawn_worker()

    def _spawn_worker(self) -> None:
        if self._proc and self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=3)

        self._cmd_q = multiprocessing.Queue()
        self._res_q = multiprocessing.Queue()
        self._proc = multiprocessing.Process(
            target=_sdk_worker,
            args=(self._cmd_q, self._res_q, NETWORK_INTERFACE),
            daemon=True,
        )
        self._proc.start()

        ready = self._res_q.get(timeout=15)
        if ready != "READY":
            raise RuntimeError(f"SDK worker 初始化失敗: {ready}")

    def _ensure_worker(self) -> None:
        if self._proc is None or not self._proc.is_alive():
            self._spawn_worker()

    def execute(self, action_id: str) -> str:
        self._ensure_worker()
        self._cmd_q.put(action_id)

        for _ in range(6):
            try:
                return self._res_q.get(timeout=0.5)
            except Exception:
                if self._proc and not self._proc.is_alive():
                    self._spawn_worker()
                    return "OK"
        return "OK"

    def emergency_stop(self) -> None:
        self.execute("emergency_stop")


def _find_usb_sink() -> str | None:
    """找 USB 輸出設備名，給 gst 播放時顯式指定。"""
    try:
        output = subprocess.check_output(
            ["pactl", "list", "sinks", "short"],
            stderr=subprocess.DEVNULL,
        ).decode()
    except Exception:
        return None

    for line in output.strip().splitlines():
        if "usb" in line.lower():
            return line.split()[1]
    return None


def _gst_play_cmd(path: Path) -> list[str]:
    sink_name = _find_usb_sink()
    if sink_name:
        return [
            "gst-launch-1.0",
            "playbin",
            f"uri=file://{path}",
            f"audio-sink=pulsesink device={sink_name}",
        ]
    return ["gst-play-1.0", "--no-interactive", str(path)]


def play_audio_blocking(name: str) -> None:
    path = AUDIO_DIR / f"{name}.mp3"
    if path.exists():
        subprocess.run(_gst_play_cmd(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


CONFIRM_KEYWORDS = ["確認", "確定", "好的", "可以", "執行", "來吧"]


def drain_audio_queue() -> None:
    """清掉積壓音頻，避免上一輪殘留回聲干擾當前識別。"""
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break


def confirm_dangerous(model: WhisperModel, desc: str) -> bool:
    """危險動作必須二次確認。"""
    play_audio_blocking("confirm")
    time.sleep(0.3)
    drain_audio_queue()

    audio_data = record_speech(timeout=8.0)
    if audio_data is None:
        play_audio_blocking("timeout")
        return False

    confirm_text = normalize_asr(transcribe(model, audio_data))

    if any(keyword in confirm_text for keyword in CONFIRM_KEYWORDS):
        return True

    if any(keyword in confirm_text for keyword in ["不", "不要", "取消", "算了", "別"]):
        play_audio_blocking("stop")
        return False

    play_audio_blocking("unknown")
    return False


def main() -> None:
    model = WhisperModel(MODEL_PATH, device="cpu", compute_type="int8")
    controller = Go2Controller()

    start_recording()
    state = State.SLEEPING

    try:
        while True:
            if state == State.SLEEPING:
                audio_data = record_speech(timeout=0.0)
                if audio_data is None:
                    continue

                text = normalize_asr(transcribe(model, audio_data))
                if not text:
                    continue

                if not check_wake_word(text):
                    continue

                play_audio_blocking("wake")
                time.sleep(0.3)
                drain_audio_queue()

                result = parse_intent(text)
                if result is not None:
                    action_id, desc = result
                else:
                    state = State.ACTIVE
                    audio_data = record_speech(timeout=ACTIVE_TIMEOUT)
                    if audio_data is None:
                        play_audio_blocking("timeout")
                        state = State.SLEEPING
                        continue

                    text = normalize_asr(transcribe(model, audio_data))
                    if not text:
                        play_audio_blocking("timeout")
                        state = State.SLEEPING
                        continue

                    if check_stop(text):
                        controller.emergency_stop()
                        play_audio_blocking("stop")
                        state = State.SLEEPING
                        continue

                    result = parse_intent(text)
                    if result is None:
                        play_audio_blocking("unknown")
                        state = State.SLEEPING
                        continue

                    action_id, desc = result

                if action_id in DANGEROUS_ACTIONS:
                    if not confirm_dangerous(model, desc):
                        state = State.SLEEPING
                        continue

                controller.execute(action_id)
                play_audio_blocking("ok")
                state = State.SLEEPING

    finally:
        stop_recording()


if __name__ == "__main__":
    main()
