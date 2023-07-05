import os

MAX_TEXTURE = 2048
debug = ""
folder_paths = [
    "D:\\FGCQ\\editor\\SkillEditor\\skill_Data\\Action\\Images\\1",
    "D:\\FGCQ\\editor\\SkillEditor\\skill_Data\\Action\\Images\\2",
    "D:\\FGCQ\\editor\\SkillEditor\\skill_Data\\Action\\Images\\8"
]

def get_txt_files(folder_path):
    txt_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.txt'):
                file_path = os.path.join(root, file)
                txt_files.append(file_path)
    return txt_files


def get_error_files(txt_files):
    errorFile = ""
    count = 0
    for file_path in txt_files:
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()  # 去除行末尾的换行符和空格
                items = line.split(';')  # 以分号分割每一行
                x = int(items[1])
                y = int(items[2])

                if MAX_TEXTURE < x or MAX_TEXTURE < y:
                    errorFile = errorFile + file_path + "\n"
                    count = count + 1
                    break
    
    return errorFile, count

for folder_path in folder_paths:
    txt_files = get_txt_files(folder_path)
    errorFile, count = get_error_files(txt_files)
    debug = debug + errorFile

with open("errorFiles.txt", "w") as file:
    file.write(debug)

print("check end")

  