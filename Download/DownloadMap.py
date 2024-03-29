
import requests
import threading
import time
import os
import tkinter as tk
from tkinter import messagebox

def submit():
    mapUrlTemplete = cdn_entry.get()
    output_folder = outPath_entry.get()
    depth = int(deptah_entry.get())
    mapUrlTemplete = mapUrlTemplete + '/{0}_{1}.jpg'
    download(output_folder, mapUrlTemplete, depth)

def mapUrlList(url_template, depth):
    file_list = []
    # 下载的预测深度
    for x in range(0, depth):
        for y in range(0, depth):
            url = url_template.format(x, y)
            file_list.append(url)
    
    return file_list

def downloadFile(url, output_folder):
    fileName = os.path.basename(url)
    output_path = os.path.join(output_folder, fileName)  # 构建输出文件路径

    if os.path.exists(output_path):
        return
    
    response = requests.get(url, stream=True)
    if response.status_code != 200:
        return

    with open(output_path, 'wb') as f:
        f.write(response.content)
        print(fileName, ' downloaded successfully.')

def download(output_folder, mapUrlTemplete, depth):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)  # 如果输出文件夹不存在，创建它

    urls = mapUrlList(mapUrlTemplete, depth)

    for url in urls:
        threads = []
        thread = threading.Thread(target=downloadFile, args=(url,output_folder,))
        threads.append(thread)
        thread.start()
        time.sleep(0.01)

    # 等待所有线程完成
    for thread in threads:
        thread.join()
        messagebox.showinfo("下载完成", f"保存为： {output_folder}")

root = tk.Tk()
root.title("下载地图")

# 设置窗口大小
root.geometry("800x600")

# 说明文本
# Label and Entry for path
cdn_label = tk.Label(root, text="地图cdn地址:", font=("Arial", 12))
cdn_label.grid(row=1, column=0)
cdn_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
cdn_entry.grid(row=1, column=1)

# Label and Entry for width
outPath_label = tk.Label(root, text="本地输出目录:", font=("Arial", 12))
outPath_label.grid(row=2, column=0)
outPath_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
outPath_entry.grid(row=2, column=1)

# Label and Entry for height
depth_label = tk.Label(root, text="预测下载的深度默认40", font=("Arial", 12))
depth_label.grid(row=3, column=0)
deptah_entry = tk.Entry(root, width=100)  # 设置输入框的宽度为20
deptah_entry.grid(row=3, column=1)

# Submit button
submit_button = tk.Button(root, text="下载", command=submit, width=50, font=("Arial", 12))
submit_button.grid(row=6, column=0, columnspan=2)
root.mainloop()