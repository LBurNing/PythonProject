import requests
from bs4 import BeautifulSoup

url = "https://cdn-bz2.jikewan.com/cqwjcq/0/map/1-26zhudong/image"
response = requests.get(url)

if response.status_code == 200:
    soup = BeautifulSoup(response.content, 'html.parser')

    resource_links = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href:
            resource_links.append(href)

    for resource_link in resource_links:
        print(resource_link)
else:
    print("Failed to retrieve the webpage.")
