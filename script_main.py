import requests
from bs4 import BeautifulSoup
import time
import json
import re
from datetime import datetime
import random

def format_datetime(news_time):
    dt_object = datetime.strptime(news_time, "%Y.%m.%d %H:%M")
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")

def get_ttv_news_list():
    # 取新聞清單
    my_headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36'
    }

    for i in range(1, 11):
        req_news = []
        # 政治, 國際, 社會
        res = requests.get(f'https://news.ttv.com.tw/category/社會/{i}', headers=my_headers)
        soup = BeautifulSoup(res.text, 'lxml')
        news_list = soup.select('article.container a')
        for news in news_list:
            news_title = news.select('div.title')[0].text.strip()
            news_time = news.select('div.time')[0].text.strip()
            news_time = format_datetime(news_time)
            link = news['href']
            # print(f'標題: {news_title}')
            # print(f'時間: {news_time}')
            # print(f'連結: {link}')

            req_news.append({'news_time': news_time, 'news_title': news_title, 'news_url': link, 'source_website': 1})
        res = requests.post('http://127.0.0.1:5000/news', json=req_news)
        print(req_news)
        # print(res.text)
        time.sleep(random.randint(1,3))


def get_ttv_news():
    # 取得待爬清單
    res = requests.post('http://127.0.0.1:5000/wait_query_list', json={'source_website': 1, 'count': 10})
    query_list = json.loads(res.text)

    # 取新聞內容
    my_headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36'
    }
    if len(query_list) == 0:
        return 0

    for query_data in query_list:
        res = requests.get(query_data['news_url'], headers=my_headers)
        soup = BeautifulSoup(res.text, 'lxml')

        # 標題
        title = soup.select("h1.mb-ht-hf")[0].text.strip()
        title = re.sub(r'\u3000', ' ', title)

        # 類別
        category = [soup.select("div#crumbs li")[-1].text]

        # 標籤
        ul = soup.select("ul.news-status > ul.tag li")
        keywords = [li.text for li in ul]
        print(keywords)

        # 抓取圖片
        imgs = soup.select("article#contentarea img")

        if len(imgs) > 1:
            src = imgs[1]['src']
        elif len(imgs) > 0:
            src = imgs[0]['src']
        else:
            src = None

        # 內文
        p = soup.select("div#newscontent > p")
        content = '\n'.join([x.text for x in p])

        # 抓取編輯
        author = re.search(r'責任編輯／([\u4e00-\u9fff]+)', content)[1]

        json_data = {'news_title': title, 'news_content': content, 'image_url': src, 'keywords': keywords, 'category': category, 'author': author, 'query_state': 2}
        response = requests.put(f'http://127.0.0.1:5000/news/{query_data['id']}', json=json_data)
        print('id:', query_data['id'], response.reason)

        time.sleep(random.randint(1,3))
    return 1

if __name__ == '__main__':
    get_ttv_news_list()
    while True:
        is_wait_qurey = get_ttv_news()
        if is_wait_qurey == 0:
            break
