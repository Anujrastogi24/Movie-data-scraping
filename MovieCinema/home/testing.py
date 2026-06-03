# import requests, time , re
# from bs4 import BeautifulSoup       
# mName = "RRR 2022"           
# print(mName)
# start_time = time.perf_counter() # start the timer
# url = "https://www.google.com/search?q="+str(mName)+"+imdb"
# r = requests.get(url)
# soup = BeautifulSoup(r.text, 'html.parser')
# link = soup.select_one('div#main .Gx5Zad.fP1Qef.xpd.EtOod.pkphOe a')
# title = link.find('div', class_="BNeawe vvjwJb AP7Wnd").text.replace(" - IMDb", "")
# print(link)
# print(title)
# imdb_url = link.attrs['href'].split('&')[0].replace('/url?q=', '')
# moviepage = requests.get(imdb_url, headers={'User-Agent': 'Mozilla/5.0'})
# soup = BeautifulSoup(moviepage.text, 'html.parser')
# #review this
# # async def description():
# title = soup.find(title)

# description_element = soup.find(
#     'meta', {'name': 'description'})
# description = description_element.get('content')
# # async def genres():
# genres_element = soup.find(
#     'div', class_="ipc-chip-list__scroller")
# genres_get = genres_element.get_text()
# genres = " ".join(re.split("(?=[A-Z])", genres_get))
# elapsed_time = time.perf_counter() - start_time # calculate the elapsed time
# print(f"Time taken 1: {elapsed_time:.6f} seconds")
# print(title)


