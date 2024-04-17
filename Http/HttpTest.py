import requests
upload_url = 'http://localhost:8001/upload'

def upload(file_path):
    files = {'file': (file_path, open(file_path, 'rb'))}
    response = requests.post(upload_url, files=files)
    print(response.text)

def download(resource_url):
    response = requests.get(resource_url)
    if response.status_code == 200:
        filename = resource_url.split('/')[-1]

        with open(filename, 'wb') as f:
            f.write(response.content)

        print(f'Resource downloaded successfully as "{filename}"')
    else:
        print('Failed to download the resource')

upload('main.ui')
download('http://localhost:8001/downloads/下载.txt')