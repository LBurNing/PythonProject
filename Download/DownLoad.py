
import requests
import os
from tqdm import tqdm
import threading
import time

#hair_0000_0_0 0000资源编号 0男女 0方向
#http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim 龙源迷失传奇的cdn地址 
#http://hscdn.dhsf.xqhuyu.com/custom/8771/webres/anim/effect/sfx_40770_0.plist 天宫传说
effectUrlTemplete = "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/effect/sfx_{0}_{1}.png"
hairUrlTemplete = "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/hair/hair_{0}_{1}_{2}.png"
monsterUrlTemplete ="http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/monster/monster_{0}_{1}_{2}.png"
npcUrlTemplete = "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/npc/npc_{0}_{1}_{2}.png"
playerUrlTemplete = "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/player/player_{0}_{1}_{2}.png"
shieldUrlTemplete ="http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/shield/shield_{0}_{1}_{2}.png"
weaponUrlTemplete ="http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/weapon/weapon_{0}_{1}_{2}.png"
wingsUrlTemplete ="http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/wings/wings_{0}_{1}_{2}.png"
mapUrlTemplete = "https://cdn-bz2.jikewan.com/cqwjcq/0/map/3-1srsimiao1ceng/image/{0}_{1}.jpg"

output_folder = "E:\PKM2PNG-main\png2pkm\\res\\龙渊迷失"  # 指定输出文件夹路径

def replace_number(number):
    if 0 <= number <= 1000:
        return f"{number:04d}"
    else:
        return str(number)
    
def unitUrlList(url_template):
    file_list = []
    for resource_number in range(0, 1000):  # 0-1000
        for sex in range(0, 2):  # 0-10
            for direction in range(0, 9):  # 0-10
                url = url_template.format(replace_number(resource_number), sex, direction)
                file_list.append(url)

                plistUrl = url.rsplit(".", 1)[0] + ".plist"
                file_list.append(plistUrl)
    
    return file_list
   
def effectUrlList(url_template):
    file_list = []
    for resource_number in range(0, 2000):  # 0-1000
        for direction in range(0, 9):  # 0-10
            url = url_template.format(replace_number(resource_number), direction)
            file_list.append(url)

            plistUrl = url.rsplit(".", 1)[0] + ".plist"
            file_list.append(plistUrl)
    
    return file_list

def mapUrlList(url_template):
    file_list = []
    for x in range(0, 40):  # 0-1000
        for y in range(0, 40):  # 0-10
            url = url_template.format(x, y)
            file_list.append(url)
    
    return file_list

def downloadFile(url):
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

def download():
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)  # 如果输出文件夹不存在，创建它

    # urls = effectUrlList(effectUrlTemplete)
    # urls = unitUrlList(playerUrlTemplete)
    # urls = unitUrlList(hairUrlTemplete)
    # urls = unitUrlList(monsterUrlTemplete)
    # urls = unitUrlList(npcUrlTemplete)
    # urls = unitUrlList(shieldUrlTemplete)
    # urls = unitUrlList(weaponUrlTemplete)
    # urls = unitUrlList(wingsUrlTemplete)
    urls = mapUrlList(mapUrlTemplete)

    for url in urls:
        threads = []
        thread = threading.Thread(target=downloadFile, args=(url,))
        threads.append(thread)
        thread.start()
        time.sleep(0.01)

    # 等待所有线程完成
    for thread in threads:
        thread.join()

download()