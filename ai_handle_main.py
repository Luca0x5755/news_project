import requests
import re
import json
import configparser

def get_token_from_config(config_path="config.ini"):
    """從 ini 檔案中讀取 token"""
    config = configparser.ConfigParser()
    config.read(config_path)
    return config["API"]["token"]

def fetch_models(token):
    """取得模型清單"""
    url = "http://localhost:3000/api/models"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("請求失敗：", e)
        return None

def fetch_news_list(count):
    """取得待處理的新聞清單"""
    url = 'http://127.0.0.1:5000/wait_ai_handle_list'
    try:
        response = requests.post(url, json={'count': count})
        return json.loads(response.text)
    except Exception as e:
        print("取得新聞清單失敗：", e)
        return []

def chat_with_model(token, content):
    """與模型互動並生成分析結果"""
    url = 'http://localhost:3000/api/chat/completions'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {
        "model": "gemma3:12b-it-qat",
        "messages": [
            {
                "role": "system",
                "content": """
                    你是一位專業的新聞分析師，擅長從新聞提取關鍵資訊。
                    1. 標題：
                    - 整理出一個可以貫穿整個文章的標題，使用肯定句，最多35個文字。
                    2. 分類：
                    - 將內容分類，並回答是屬於哪一項，政治、國際、地方、社會、娛樂、生活、氣象、健康、體育、財經、旅遊、科技。
                    3. 關鍵字：
                    - 提取最多5個核心的名詞，包含團體、政黨、名人、技術。
                    - 名人需判斷是否為政治人物，是政治人物需加上政黨名稱。
                    - 使用", "作為關鍵字的間格符號。
                    4. 語意分析：
                    - 分析內容的情感類別，並回答是正面、負面還是中立。
                    5. 將以上結果轉換成json格式
                    - {"title": "標題結果", "category": ["分類結果1", "分類結果2"], "keyword": ["關鍵字結果1", "關鍵字結果2"], "sentiment_analysis": "語意分析結果"}
                """
            },
            {
                "role": "user",
                "content": content
            }
        ]
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        return response.json()
    except Exception as e:
        print("模型互動失敗：", e)
        return None

def process_and_add_ai_news(token, news_list):
    """處理新聞並新增至 AI 分析結果表"""
    api_url = "http://127.0.0.1:5000/add_ai_news"
    for news in news_list:
        jsondata = chat_with_model(token, news['news_content'])
        if not jsondata:
            continue

        try:
            content1 = jsondata['choices'][0]['message']['content']
            re_obj = re.search(r'```json(.*?)```', content1, re.DOTALL)
            result_json = json.loads(re_obj[1])

            data = {"news_id": news['id'], **result_json}
            response = requests.post(api_url, json=data)

            if response.status_code == 201:
                print("新增成功:", news['id'], response.json())
            else:
                print("新增失敗:", response.status_code, response.json())
        except Exception as e:
            print("處理失敗：", news['id'], e)

if __name__ == "__main__":
    token = get_token_from_config()
    models = fetch_models(token)
    if models:
        print("取得的模型：", models)

    while True:
        news_list = fetch_news_list(count=10)
        if news_list:
            process_and_add_ai_news(token, news_list)
        else:
            break
