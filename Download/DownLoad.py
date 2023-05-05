import requests
import os
from tqdm import tqdm

urls = [
    "http://localhost:8800/downloads/defaultfont.kui",
    "http://localhost:8800/downloads/icon_otheratlas.kui",
    "http://localhost:8800/downloads/rolelistatlas.kui",
    "http://localhost:8800/downloads/commercialactivityatlas.kui",
    "http://localhost:8800/downloads/headatlas.kui",
    "http://localhost:8800/downloads/debugloginui.kui",
    "http://localhost:8800/downloads/commercialactivitypublicatlas.kui",
]

def downloadFile(url):
    response = requests.get(url, stream=True)
    fileName = os.path.basename(url)
    file_size = int(response.headers.get('Content-Length', 0))
    progress = tqdm(response.iter_content(102400), f"Downloading {fileName}", total=file_size, unit="M", unit_scale=True, unit_divisor=102400)

    # if response.status_code == 200:
    with open(fileName, 'wb') as f:
        for data in progress:
            f.write(data)

        print('file downloaded successfully.')
    # else:
    #     print('Failed to download file, code: ', response.status_code)

def download():
    for url in urls:
        downloadFile(url)

download()
