import os
from PIL import Image
import tkinter as tk
from tkinter import messagebox

def submit():
    image_folder = path_entry.get()
    image_width = int(width_entry.get())
    image_height = int(height_entry.get())
    num_columns = int(cols_entry.get())
    num_rows = int(rows_entry.get())

    # 支持的图片格式
    supported_ext = ['.jpg', '.jpeg', '.png']

    image_files = []
    for root, dirs, files in os.walk(image_folder):
        for fileName in files:
            ext = os.path.splitext(fileName)[1].lower()
            if ext in supported_ext and not fileName.startswith('__out__'):
                image_files.append(os.path.join(root, fileName))

    if not image_files:
        messagebox.showerror("错误", "未找到支持的图片文件！")
        return

    # 根据第一张图片的后缀决定输出格式
    first_ext = os.path.splitext(image_files[0])[1].lower()
    output_ext = first_ext
    output_path = os.path.join(image_folder, f'__out__{output_ext}')

    # 创建一个新的大图
    mode = 'RGBA' if output_ext == '.png' else 'RGB'
    result_image = Image.new(mode, (num_columns * image_width, num_rows * image_height))

    # 按行列粘贴图片
    for i in range(len(image_files)):
        row = i // num_columns
        col = i % num_columns
        img_path = image_files[i]
        img = Image.open(img_path)
        img = img.resize((image_width, image_height), Image.LANCZOS)
        result_image.paste(img, (col * image_width, row * image_height))

    # 保存拼接后的大图
    result_image.save(output_path)
    messagebox.showinfo("拼接完成", f"保存为 {output_path}")

root = tk.Tk()
root.title("合并碎图")
root.geometry("800x600")

info_text = """文件命名格式必须是 0_0、0_1... --- 1_0、1_1... 目前支持jpg和png"""
info_label = tk.Label(root, text=info_text, justify="left", font=("Arial", 12))
info_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

# 路径输入
tk.Label(root, text="图片所在路径:", font=("Arial", 12)).grid(row=1, column=0)
path_entry = tk.Entry(root, width=100)
path_entry.grid(row=1, column=1)

# 宽
tk.Label(root, text="宽:", font=("Arial", 12)).grid(row=2, column=0)
width_entry = tk.Entry(root, width=100)
width_entry.grid(row=2, column=1)

# 高
tk.Label(root, text="高:", font=("Arial", 12)).grid(row=3, column=0)
height_entry = tk.Entry(root, width=100)
height_entry.grid(row=3, column=1)

# 列
tk.Label(root, text="列:", font=("Arial", 12)).grid(row=4, column=0)
cols_entry = tk.Entry(root, width=100)
cols_entry.grid(row=4, column=1)

# 行
tk.Label(root, text="行:", font=("Arial", 12)).grid(row=5, column=0)
rows_entry = tk.Entry(root, width=100)
rows_entry.grid(row=5, column=1)

# 合并按钮
tk.Button(root, text="合并", command=submit, width=50, font=("Arial", 12)).grid(row=6, column=0, columnspan=2)

root.mainloop()