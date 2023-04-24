from PIL import Image
import os

folder_path = "D:\\FGCQ\\editor\\SkillEditor\\skill_Data\\Action\\Images\\6"
count = 0

# 打开文件，以追加模式写入输出结果
with open("output.txt", "a") as f:
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                with Image.open(filepath) as img:
                    width, height = img.size
                    if width >= 1024 and height >= 1024:
                        count = count + 1
                        # 将输出结果写入文件
                        f.write(f"{filepath}: {width} x {height}\n")
            except:
                pass

# 输出裁切图片的数量
with open("output.txt", "a") as f:
    f.write(f"count: {count}\n")
    
print(f"count: {count}")