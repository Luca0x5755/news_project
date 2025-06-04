import requests
import re
import json
import configparser
import time
from configparser import ConfigParser
import traceback

config = ConfigParser()
config.read('config.ini')
WEB_API_ADDRESS = f"{config['WEB_SERVER']['host']}:{config['WEB_SERVER']['port']}"

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

def fetch_news_list(count, model):
    """取得待處理的新聞清單"""
    url = f'http://{WEB_API_ADDRESS}/wait_ai_handle_list'
    try:
        response = requests.post(url, json={'count': count, 'model': model})
        return json.loads(response.text)
    except Exception as e:
        print("取得新聞清單失敗：", e)
        return []

class ChatSession:
    def __init__(self, token, model):
        self.url = 'http://localhost:3000/api/chat/completions'
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        self.model = model
        self.messages = [
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
4. 語意分析：
- 分析內容的情感類別，並回答是正面、負面還是中立。
5. 將以上結果轉換成json格式
- {"title": "標題結果", "category": ["分類結果1", "分類結果2"], "keywords": ["關鍵字結果1", "關鍵字結果2"], "sentiment_analysis": "正面、負面、中立", "sentiment_analysis_detail": "分析結果"}
                """
            }
        ]

    def chat(self, user_content):
        self.messages.append({"role": "user", "content": user_content})
        data = {
            "model": self.model,
            "messages": self.messages
        }
        try:
            response = requests.post(self.url, headers=self.headers, json=data)
            result = response.json()
            # 將模型回應加入對話歷史以維持上下文
            if "choices" in result and len(result["choices"]) > 0:
                self.messages.append({
                    "role": "assistant",
                    "content": result["choices"][0]["message"]["content"]
                })
            return result
        except Exception as e:
            print("模型互動失敗：", e)
            return None


def process_and_add_ai_news(token, news_list, model):
    """處理新聞並新增至 AI 分析結果表"""
    api_url = f"http://{WEB_API_ADDRESS}/add_ai_news"

    session = ChatSession(token=token, model=model)

    for news in news_list:
        jsondata = session.chat(news['news_content'])
        if not jsondata:
            continue
        try:
            content1 = jsondata['choices'][0]['message']['content']
            re_obj = re.search(r'```json(.*?)```', content1, re.DOTALL)
            result_json = json.loads(re_obj[1])
            print(result_json)
            data = {"news_id": news['id'], 'model': model, **result_json}
            response = requests.post(api_url, json=data)

            if response.status_code == 201:
                print("新增成功:", news['id'], response.json())
            else:
                print("新增失敗:", response.status_code, response.json())
        except Exception as e:
            traceback.print_exc()
            print("處理失敗：", news['id'], e)

if __name__ == "__main__":
    token = get_token_from_config()
    models = fetch_models(token)
    if models:
        print("取得的模型：", models)

    model = 'gemma3:4b-it-qat' # 使用的模型
    # model = 'gemma3:12b-it-qat'
    while True:
        t1 = time.time()
        news_list = fetch_news_list(count=10, model=model)

        if news_list:
            process_and_add_ai_news(token, news_list, model)
        else:
            break

        t2 = time.time()
        print('\n\n用時(s):',  t2-t1)
