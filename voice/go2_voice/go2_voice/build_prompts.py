#!/usr/bin/env python3
"""
把固定反饋語句預生成成 mp3。
運行一次就夠，後面主程式只播本地檔案。
"""

from pathlib import Path

import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "audio"

PROMPTS = {
    # 系統提示音
    "wake": "我在，請說指令",
    "ok": "好的",
    "unknown": "沒聽懂，請再說一次",
    "stop": "好的，已經停下來了",
    "timeout": "沒有新的指令，我先休息啦",
    "confirm": "這個動作有點危險，請再確認一次",
    # 導覽點介紹詞
    "history_museum_intro": "這裡是南京大學信息管理學院院史館，主要展示學院的發展歷程、辦學成果與重要史料，幫助師生與訪客了解學院的學術傳承與歷史脈絡。它不只是展示空間，也具有保存院史文獻與推廣學院文化的功能。",
    "archive_room_intro": "這裡是資料室，主要負責整理、保存與提供相關歷史資料、檔案與文獻，方便學院師生進行查閱與研究。它是學院資料管理與史料保存的重要場所。",
    "school_of_classified_intro": "這裡是南京大學國家保密學院，依托信息管理學院建設，主要培養保密與信息安全相關人才。其教學內容結合理論、技術與實務，並設有相關實驗與訓練空間。",
    "hci_lab_intro": "這裡是人機交互實驗室，聚焦人與智能系統的互動研究，涵蓋可視化、VR仿真交互與眼動分析等方向，致力於探索更自然、更高效的智慧互動方式。",
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, text in PROMPTS.items():
        target = OUTPUT_DIR / f"{name}.mp3"
        communicator = edge_tts.Communicate(text=text, voice=VOICE)
        communicator.save_sync(str(target))
        print(f"已生成: {target.name}")


if __name__ == "__main__":
    main()
