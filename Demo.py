import requests
import os
from bs4 import BeautifulSoup
import time
 
def download(url, page):
    html = requests.get(url).text
    soup = BeautifulSoup(html, 'html.parser')
    list = soup.select('div.ball_box01 ul li')
    ball = []
    for li in list:
        ball.append(li.string)
    write_to_excel(page, ball, url)
    print(f"第{page}期开奖结果录入完成")
 
 
def write_to_excel(page, ball, url):
    if len(ball) == 0:
        print(f"第{page}期开奖结果录入失败, retrying...")
        download(url, page)
        return
    
    f = open('双色球开奖结果.csv', 'a', encoding='utf_8_sig')
    f.write(f'第{page}期,{ball[0]},{ball[1]},{ball[2]},{ball[3]},{ball[4]},{ball[5]},{ball[6]}\n')
    f.close()
 
 
def turn_page():
    url = "http://kaijiang.500.com/ssq.shtml"
    html = requests.get(url).text
    soup = BeautifulSoup(html, 'html.parser')
    pageList = soup.select("div.iSelectList a")
 
    for p in pageList:
        url = p['href']
        page = p.string
        download(url, page)
 
 
def main():
    if os.path.exists('双色球开奖结果.csv'):
        os.remove('双色球开奖结果.csv')
    turn_page()
 
 
if __name__ == '__main__':
    main()