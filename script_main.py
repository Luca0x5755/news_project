import requests
from bs4 import BeautifulSoup
import time
import json
import re
from datetime import datetime
import random
from configparser import ConfigParser

config = ConfigParser()
config.read('config.ini')
WEB_API_ADDRESS = f"{config['WEB_SERVER']['host']}:{config['WEB_SERVER']['port']}"

def format_datetime(news_time):
    dt_object = datetime.strptime(news_time, "%Y.%m.%d %H:%M")
    return dt_object.strftime("%Y-%m-%d %H:%M:%S")

def get_ttv_news_list():
    # 取新聞清單
    my_headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36'
    }

    category_list = ['政治', '國際', '社會', '娛樂', '生活', '氣象', '地方', '健康', '體育', '財經']
    for category in category_list:
        # 1~40 ok
        for i in range(40, 60):
            req_news = []
            # 政治, 國際, 社會
            res = requests.get(f'https://news.ttv.com.tw/category/{category}/{i}', headers=my_headers)
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
            res = requests.post(f'http://{WEB_API_ADDRESS}/news', json=req_news)
            # print(req_news)

            # 確保清單不會一直重複查詢
            res_objs = json.loads(res.text)
            success_count = len(res_objs['success'])
            errors_count = len(res_objs['errors'])
            print(f'上傳成功: {success_count}, 上傳失敗: {errors_count}')
            time.sleep(random.randint(1,3))
            # if success_count == 0:
            #     print(f'{category}類別已查詢完成')
            #     break

def get_ttv_news():
    # 取得待爬清單
    res = requests.post(f'http://{WEB_API_ADDRESS}/wait_query_list', json={'source_website': 1, 'count': 10})
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
        author = re.search(r'責任編輯／([\u4e00-\u9fff]+)', content)
        author = author[1] if author else None

        json_data = {'news_title': title, 'news_content': content, 'image_url': src, 'keywords': keywords, 'category': category, 'author': author, 'query_state': 2}
        response = requests.put(f'http://{WEB_API_ADDRESS}/news/{query_data['id']}', json=json_data)
        print('id:', query_data['id'], response.reason)

        time.sleep(random.randint(2,7))
    return 1

def get_setn_news():
    # max 1664942, min 1661463
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    }
    for i in range(1661463, 1660000, -1):
        link = f'https://www.setn.com//News.aspx?NewsID={i}&utm_campaign=viewallnews'
        response = requests.get(link, headers=headers)
        soup = BeautifulSoup(response.text, 'lxml')

        # page_date = soup.select('time.page_date')[0].text
        # Content1 = soup.select('div#Content1 > p')

        ld_json_scripts = soup.find('script', type='application/ld+json')
        data = json.loads(ld_json_scripts.string)

        soup_news_title = soup.select('h1.news-title-3')
        if soup_news_title == []:
            continue
        news_title = soup_news_title[0].text

        # 內文
        content = data['description']

        # 抓取編輯
        # 社會中心／黃韻璇報導
        # 政治中心／綜合報導
        # 生活中心／王文承報導
        # 記者林意筑／台中報導
        # 記者廖宜德、張裕坤、張展誌／雲林報導
        # text = '生活中心／王文承報導'
        # author = re.search(r'記者([\u4e00-\u9fff]+?)[、／]|中心／([\u4e00-\u9fff]+?)[報導、]', text)
        # author = author[1] if author[1] else author[2]
        author = None
        for k, v in data['author'].items():
            if k == 'name':
                author = v


        # 抓取圖片
        # imgs = soup.select("div#Content1 img")
        # src = None
        # if len(imgs) > 0:
        #     src = imgs[0]['src']

        src = None
        for k, v in data['image'].items():
            if k == 'url':
                src = v

        # 日期時間
        dt = datetime.fromisoformat(data['datePublished'])
        news_time = dt.strftime("%Y-%m-%d %H:%M:%S")

        keywords = data['keywords']
        category = data['articleSection']

        json_data = [{'news_title': news_title, 'news_content': content, 'image_url': src, 'keywords': keywords, 'category': category, 'author': author, 'query_state': 2, 'news_url': link, 'source_website': 2, 'news_time': news_time}]
        res = requests.post(f'http://{WEB_API_ADDRESS}/news', json=json_data)
        print(json.loads(res.text))
        time.sleep(random.randint(2,4))

# def main():

if __name__ == '__main__':
    get_ttv_news_list()
    while True:
        is_wait_qurey = get_ttv_news()
        if is_wait_qurey == 0:
            break

    # get_setn_news()
