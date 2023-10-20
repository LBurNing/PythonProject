#!/usr/bin/python

import os
import sys
import chardet

dir = sys.argv[1]

for root, dirs, files in os.walk(dir):
    for file in files:
        if file.endswith(".lua"):  # 只检测 .lua 文件
            file = os.path.join(root, file)
            f = open(file, "rb")
            s = f.read()
            f.close()
            
            encoding = chardet.detect(s)["encoding"]
            if encoding != "ascii" and encoding != "utf-8":                
                print(file, ": ", encoding)
