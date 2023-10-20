import sys
import os
from PIL import Image, ImageOps
import concurrent.futures

debug = sys.gettrace()
if debug:
    print("Debug模式\n")
    input_file = 'D:/WXWork/Cache/WXWork/1688854848508957/Cache/File/2023-10/shengshouzhanchang.jpg'
    output_file = 'output.jpg'
else:
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    print("Release模式\ninput_file: ", input_file, " output_file: ", output_file)

def bmp_to_jpg(input_file, output_file):
    with Image.open(input_file) as img:
        img.convert("RGB").save(output_file, "JPEG")

bmp_to_jpg(input_file, output_file)