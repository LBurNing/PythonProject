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
    output_path = image_folder + '\__out__.jpg'

    image_files = []
    for root, dirs, files in os.walk(image_folder):
        for fileName in files:
            if fileName.endswith('.jpg') and not fileName.startswith('__out__'):
                image_files.append(os.path.join(root, fileName))

    # 创建一个新的大图
    result_image = Image.new('RGB', (num_columns * image_width, num_rows * image_height))
    length = len(image_files)
    for i in range(len(image_files)):
        row = i // num_columns
        col = i % num_columns
        img_path = os.path.join(image_folder, "{}_{}.jpg".format(row, col))
        img = Image.open(img_path)
        img = img.resize((image_width, image_height), Image.LANCZOS)
        result_image.paste(img, (col * image_width, row * image_height))

    # # 保存拼接后的大图
    result_image.save(output_path)
    messagebox.showinfo("拼接完成", f"保存为 {output_path}")

root = tk.Tk()
root.title("合并碎图")

# 设置窗口大小
root.geometry("800x600")

# 说明文本
info_text = """文件命名格式必须是 0_0、0_1... --- 1_0、1_1... --- 2_0、2_1... 目前只支持jpg"""
info_label = tk.Label(root, text=info_text, justify="left", font=("Arial", 12))
info_label.grid(row=0, column=0, columnspan=2, padx=10, pady=10)

# Label and Entry for path
path_label = tk.Label(root, text="图片所在路径:", font=("Arial", 12))
path_label.grid(row=1, column=0)
path_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
path_entry.grid(row=1, column=1)

# Label and Entry for width
width_label = tk.Label(root, text="宽:", font=("Arial", 12))
width_label.grid(row=2, column=0)
width_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
width_entry.grid(row=2, column=1)

# Label and Entry for height
height_label = tk.Label(root, text="高:", font=("Arial", 12))
height_label.grid(row=3, column=0)
height_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
height_entry.grid(row=3, column=1)

# Label and Entry for cols
cols_label = tk.Label(root, text="列:", font=("Arial", 12))
cols_label.grid(row=4, column=0)
cols_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
cols_entry.grid(row=4, column=1)

# Label and Entry for rows
rows_label = tk.Label(root, text="行:", font=("Arial", 12))
rows_label.grid(row=5, column=0)
rows_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
rows_entry.grid(row=5, column=1)

# Submit button
submit_button = tk.Button(root, text="合并", command=submit, width=50, font=("Arial", 12))
submit_button.grid(row=6, column=0, columnspan=2)
root.mainloop()
