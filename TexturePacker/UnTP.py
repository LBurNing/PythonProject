#!python
import os,sys
import plistlib
from PIL import Image

def gen_png_from_plist(plist_filename, png_filename):
    file_path = plist_filename.replace('.plist', '')
    big_image = Image.open(png_filename)

    # 打开要读取的.plist文件
    with open(plist_filename, 'rb') as file:
        # 调用load方法来解析.plist文件
        root = plistlib.load(file)

    frames = root['frames']
    to_list = lambda x: x.replace('{','').replace('}','').split(',')
    to_int = lambda x:int(x)
    for frame in frames:
        framename = frame.replace('.png', '')
        size = frames[frame]['sourceColorRect']
        size = to_list(size)
        size = list(map(to_int, size))

        spriteSize = frames[frame]['sourceSize']
        spriteSize = to_list(spriteSize)
        spriteSize = list(map(to_int, spriteSize))

        textureRect = frames[frame]['frame']
        textureRect = to_list(textureRect)
        textureRect = list(map(to_int, textureRect))

        result_box = textureRect
        result_image = Image.new('RGBA', spriteSize, 0)
        if frames[frame]['rotated']:
            result_box[0] = int(textureRect[0])
            result_box[1] = int(textureRect[1])
            result_box[2] = int(textureRect[0] + textureRect[3])
            result_box[3] = int(textureRect[1] + textureRect[2])
        else:
            result_box[0] = int(textureRect[0])
            result_box[1] = int(textureRect[1])
            result_box[2] = int(textureRect[0] + textureRect[2])
            result_box[3] = int(textureRect[1] + textureRect[3])
        
        rect_on_big = big_image.crop(result_box)
        if frames[frame]['rotated']:
            rect_on_big = rect_on_big.transpose(Image.ROTATE_90)
        result_image.paste(rect_on_big)
        
        if not os.path.isdir(file_path):
            os.mkdir(file_path)
        
        outfile = (file_path+'/' + framename+'.png')
        print(outfile, "generated")
        result_image.save(outfile)

plistPath = "E:\PKM2PNG-main\png2pkm\png2pkm-master\pvr\plist.plist"
pngPath = "E:\PKM2PNG-main\png2pkm\png2pkm-master\pvr\sheet.png"
gen_png_from_plist(plistPath, pngPath)