# from django.contrib.postgres import *
from django.shortcuts import render 
from home.models import Movie
from bs4 import BeautifulSoup
import requests , re , time , concurrent.futures 



def searchdata(request):
    if 'Title' in request.POST:
        Title = request.POST['Title']
        print(Title)
        if len(Title) < 4:
            return render(request, 'index.html')
        else:
            if Movie.objects.filter(Title__contains=Title):
                queryset = Movie.objects.filter(Title__contains=Title)
                cast_Section = eval(queryset.values('cast')[0]['cast'])
                dlink_list = eval(queryset.values('dLink')[0]['dLink'])
                mlink_list = eval(queryset.values('mLink')[0]['mLink'])
                tlink_list = eval(queryset.values('tLink')[0]['tLink'])
                return render(request, 'movie.html', {"queryset": queryset, "casts": cast_Section,  "dLink": dlink_list, "mLink": mlink_list, "tLink": tlink_list})
            
            else:
                mName = (Title)
                if True:
                    def task1(mName):
                        print("task 1 is start")
                        start_time = time.perf_counter() # start the timer
                        url = "https://www.google.com/search?q="+str(mName)+"+imdb"
                        r = requests.get(url)
                        soup = BeautifulSoup(r.text, 'html.parser')
                        link = soup.select_one('div#main .Gx5Zad.fP1Qef.xpd.EtOod.pkphOe a')
                        title = link.find('div', class_="BNeawe vvjwJb AP7Wnd").text.replace(" - IMDb", "")
                        imdb_url = link.attrs['href'].split('&')[0].replace('/url?q=', '')
                        moviepage = requests.get(imdb_url, headers={'User-Agent': 'Mozilla/5.0'})
                        soup = BeautifulSoup(moviepage.text, 'html.parser')

                        # async def description():
                        description_element = soup.find(
                            'meta', {'name': 'description'})
                        description = description_element.get('content')
                        # async def genres():
                        genres_element = soup.find(
                            'div', class_="ipc-chip-list__scroller")
                        genres_get = genres_element.get_text()
                        genres = " ".join(re.split("(?=[A-Z])", genres_get))
                        elapsed_time = time.perf_counter() - start_time # calculate the elapsed time
                        print(f"Time taken 1: {elapsed_time:.6f} seconds")
                        return title,description,genres
                        
                    def task2(mName):
                        print("task 2 is start")
                        start_time = time.perf_counter() # start the timer

                        url = "https://www.google.com/search?q="+mName+"+rotten+tomatoes"
                        r = requests.get(url)
                        soup1 = BeautifulSoup(r.text, 'html.parser')
                        link1 = soup1.select_one('div#main .Gx5Zad.fP1Qef.xpd.EtOod.pkphOe a')
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        main_url = link1.attrs['href'].split('&')[0].replace('/url?q=', '')
                        from concurrent.futures import ThreadPoolExecutor
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        page = requests.get(main_url, headers=headers)
                        soup = BeautifulSoup(page.text, 'html.parser')


                        movPage = soup.find('body').find('main', id='main_container')
                        if True:
                            castSection = movPage.find('section', id="cast-and-crew").find_all('img', loading="lazy")
                            castSection = set(castSection)
                            cast_Section = []
                            def task(img):
                                name = img['alt']
                                try:
                                    imageUrls = img['src'].split('/v2/')[1]
                                except: 
                                    url = "https://www.google.com/search?q=" +str(name)+" imdb"
                                    print(url)
                                    Cr = requests.get(url)
                                    soupC = BeautifulSoup(Cr.text, 'html.parser')
                                    linkC = soupC.select_one('div#main .Gx5Zad.fP1Qef.xpd.EtOod.pkphOe a').get('href')

                                    # cleaning link
                                    import urllib.parse
                                    parsed_urlC = urllib.parse.urlparse(linkC)

                                    # Get the main link by accessing the 'q' query parameter
                                    main_urlC = parsed_urlC.query.split('&')[0].split('=')[1]
                                    headers = {'User-Agent': 'Mozilla/5.0'}
                                    moviepage = requests.get(main_urlC, headers=headers)
                                    soup = BeautifulSoup(moviepage.text, 'html.parser')
                                    try:
                                        eager_image = soup.find('img', {'loading': 'eager'})['src']
                                        imageUrls = eager_image.replace("_UX140_CR0,0,140,207_", "_UX280_")
                                    except:
                                        imageUrls = "http://127.0.0.1:8000/static/img/Moviecinema.jpg"
                                    
                                else: 
                                    imageUrls = "http://127.0.0.1:8000/static/img/Moviecinema.jpg"
                                sets = {"urls": (imageUrls), "casts": name}
                                cast_Section.append(sets)
                            with ThreadPoolExecutor() as executor:
                                executor.map(task, castSection)
                            
                            try:
                                image = (movPage.find('img')[
                                    'src']).split('/v2/')[1]

                            except:
                                image = (movPage.find(
                                    'img', {'data-qa': 'photos-carousel-img'})['src']).split('/v2/')[1]
                            elapsed_time = time.perf_counter() - start_time # calculate the elapsed time
                            print(f"Time taken 2: {elapsed_time:.6f} seconds")
                            return image, cast_Section
                        
                    def task3(mName):
                        
                        try:
                            print("task 3 is start")
                            start_time = time.perf_counter() # start the timer
                            

                            # Using the requests library to make an HTTP request to the FilePursuit URL
                            main_url = 'https://filepursuit.com/pursuit?q='+mName+'&type=video&sort=datedesc'
                            print(main_url)

                            # Parsing the HTML response with BeautifulSoup
                            headers = {'User-Agent': 'Mozilla/5.0'}
                            moviepage = requests.get(
                                main_url, headers=headers)
                            soup = BeautifulSoup(
                                moviepage.content, 'html.parser', from_encoding="utf-8")

                            links = soup.find_all(
                                'a', attrs={'data-toggle': 'tooltip'})
                            # Looping through the results to find valid movie links
                            urls = [link.get('onclick')
                                    for link in links[2:]]
                            movie_links = [l.split("'")[1] for l in urls]
                            # print(movie_links)

                            # Checking the Content-Type and Content-Length headers of the movie links to verify that they are valid
                            import threading

                            mLink = []
                            tLink = []
                            dLink = []

                            def process_mlinks(mlinks):
                                try:
                                    response = requests.head(
                                        mlinks, timeout=30)
                                    if response.status_code == 200:
                                        if response.headers['Content-Type'] == 'video/mp4':
                                            minutes = int(
                                                response.headers['Content-Length']) / (1024 * 1024 * 8) / 60 * 60
                                            if minutes >= 30:
                                                mLink.append(mlinks)
                                            else:
                                                tLink.append(mlinks)
                                        else:
                                            dLink.append(mlinks)
                                except (requests.exceptions.Timeout, requests.exceptions.RequestException):
                                    pass

                            threads = []
                            for mlinks in movie_links:
                                t = threading.Thread(
                                    target=process_mlinks, args=(mlinks,))
                                threads.append(t)

                            for t in threads:
                                t.start()

                            for t in threads:
                                t.join()

                            mLink = list(set(mLink))
                            tLink = list(set(tLink))
                            dLink = list(set(dLink))
                            elapsed_time = time.perf_counter() - start_time # calculate the elapsed time
                            print(f"Time taken 3: {elapsed_time:.6f} seconds")
                            return mLink,tLink,dLink
                            
                        except:
                            print("urls block problem")
                        
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        start_time = time.perf_counter() # start the timer
                        d1 = executor.submit(task1, mName) 
                        d2 = executor.submit(task2, mName) 
                        d3 = executor.submit(task3, mName) 
                        title = d1.result()[0]
                        description = d1.result()[1]
                        # genres = d1[0][2]
                        image_link = d2.result()[0]
                        cast_Section = d2.result()[1]
                        mLink = d3.result()[0]
                        tLink = d3.result()[1]
                        dLink = d3.result()[2]
 
                        Movie.objects.update_or_create(Title=title, description=description, image=image_link, cast=cast_Section, mLink=mLink, dLink=dLink, tLink=tLink)
                        queryset = Movie.objects.filter(Title__contains=title)
                        cast_Section = eval(queryset.values('cast')[0]['cast'])
                        dlink_list = eval(queryset.values('dLink')[0]['dLink'])
                        mlink_list = eval(queryset.values('mLink')[0]['mLink'])
                        tlink_list = eval(queryset.values('tLink')[0]['tLink'])
                        elapsed_time = time.perf_counter() - start_time # calculate the elapsed time
                        print(f"Total Time taken : {elapsed_time:.6f} seconds")
                        return render(request, 'movie.html', {"queryset": queryset, "casts": cast_Section,  "dLink": dlink_list, "mLink": mlink_list, "tLink": tlink_list})

                # except:
                #     return render(request, 'search.html')
    else:
        return render(request, 'index.html')
