import os

folder_path = r"C:\Users\lihehui\Desktop\Map\地狱烈焰系列五dt02层\地狱烈焰系列五层\Maps\map\tiles\STHUOLONG3"

files = sorted(os.listdir(folder_path))

# 1️⃣ 先改为临时名字，避免冲突
for filename in files:
    full_path = os.path.join(folder_path, filename)
    if not os.path.isfile(full_path):
        continue
    os.rename(full_path, full_path + ".tmp")

# 2️⃣ 再改为最终名字
for filename in os.listdir(folder_path):
    if not filename.endswith(".tmp"):
        continue
    full_path = os.path.join(folder_path, filename)
    name, ext = os.path.splitext(filename[:-4])  # 去掉 .tmp
    parts = name.split('_')
    if len(parts) != 2:
        continue
    first, second = int(parts[0]), int(parts[1])

    # 你的映射规则
    if first == 1 and 0 <= second <= 9:
        new_name = f"0_{second}.png"
    elif first == 1 and second >= 10:
        new_name = f"1_{second-10}.png"
    elif 2 <= first <= 10:
        new_name = f"{first-1}_{second}.png"
    else:
        new_name = f"{first}_{second}.png"

    new_path = os.path.join(folder_path, new_name)
    os.rename(full_path, new_path)
    print(f"{filename} -> {new_name}")