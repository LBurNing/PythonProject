import os
from pydub import AudioSegment

def enhance_mp3_volume(folder_path, db_increase=6):
    # 遍历文件夹
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".mp3"):
                file_path = os.path.join(root, file)
                print(f"处理文件: {file_path}")

                try:
                    # 读取 mp3
                    sound = AudioSegment.from_mp3(file_path)
                    # 提升音量
                    louder_sound = sound + db_increase
                    # 覆盖保存
                    louder_sound.export(file_path, format="mp3")
                    print(f"已增强音量并覆盖保存: {file_path}")
                except Exception as e:
                    print(f"处理失败 {file_path}: {e}")

if __name__ == "__main__":
    folder = input("请输入文件夹路径: ").strip()
    enhance_mp3_volume(folder, db_increase=6)