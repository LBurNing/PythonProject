import sys
import os
from PIL import Image, ImageOps
import concurrent.futures

if len(sys.argv) >= 3:
    print("Release模式\n")
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    print("Release模式\ninput_file: ", input_file, " output_file: ", output_file)
else:
    input_file = r'C:\Users\lihehui\Desktop\9张地图\276号地图月牙村落\276号地图牙村落\原图\map.bmp'
    output_file = r'C:\Users\lihehui\Desktop\月牙村落.jpg'
    print("Debug模式\ninput_file: ", input_file, " output_file: ", output_file)

def bmp_to_jpg(input_file, output_file):
    with Image.open(input_file) as img:
        img.convert("RGB").save(output_file, "JPEG")

bmp_to_jpg(input_file, output_file)