
import requests
import os
from tqdm import tqdm

urls = [
    #hair_0000_0_0 0000资源编号 0男女 0方向
    #http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim 某个传奇的cdn地址
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/effect/sfx_0006_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/effect/sfx_0006_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/hair/hair_0000_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/hair/hair_0000_0_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/monster/monster_1000_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/monster/monster_1000_0_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/npc/npc_0000_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/npc/npc_0000_0_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/player/player_0001_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/player/player_0001_0_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/shield/shield_0001_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/shield/shield_0001_0_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/weapon/weapon_0001_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/weapon/weapon_0001_0_0.plist",

    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/wings/wings_0020_0_0.png",
    "http://hscdn.dhsf.xqhuyu.com/dhsf/box_res/anim/wings/wings_0020_0_0.plist",
]

def downloadFile(url):
    response = requests.get(url, stream=True)
    fileName = os.path.basename(url)

    with open(fileName, 'wb') as f:
        f.write(response.content)
        print(fileName, ' downloaded successfully.')

def download():
    for url in urls:
        downloadFile(url)

download()