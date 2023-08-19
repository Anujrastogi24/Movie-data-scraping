import requests
from bs4 import BeautifulSoup
import concurrent.futures ,os

num = 1
headers = {'User-Agent': 'Mozilla/5.0'}

# Create a cache dictionary
cache = {}

def fetch_page(url):
    # Check if the page is already cached
    if url in cache:
        return cache[url]

    # Fetch the page and store it in the cache
    page = requests.get(url, headers=headers)
    cache[url] = page.text

    return page.text

def process_page(num):
    url = "https://4ulinks.net/" + str(num)
    # url = "https://m4u.skin/number/" + str(num)

    # Fetch the page using the cache
    page_text = fetch_page(url)

    soup = BeautifulSoup(page_text, 'html.parser')
    links = soup.findAll('a', attrs={'target': '_blank'})
    if len(links) != 0:
        for link in links:
            link = link['href']
            if link.find("https://megaup.net") != -1:
                file_name = os.path.basename(link)
                for link in links:
                    link = link['href']
                    if link.find("https://pandafiles.com") != -1:
                         print(file_name,", ",link ,", ", url)



with concurrent.futures.ThreadPoolExecutor() as executor:
    # Create a list of future objects for each page to be processed
    futures = [executor.submit(process_page, i) for i in range(50875, 52962)]
