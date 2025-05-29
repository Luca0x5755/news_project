from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime
import enum

app = Flask(__name__)
DATABASE = 'news.db'


SOURCE_WEBSITE_ENUM = {
    1: "台視",
}

# 初始化資料庫
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # news 表
        cursor.execute('''
        CREATE TABLE news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_time DATETIME NOT NULL,          -- 新聞時間
            news_title VARCHAR(50) NOT NULL,     -- 新聞標題
            news_content TEXT,                   -- 新聞內容
            image_url TEXT,                      -- 圖片連結
            news_url TEXT NOT NULL,              -- 新聞連結
            source_website INTEGER NOT NULL, -- 來源網站
            query_state INTEGER DEFAULT 0        -- 查詢狀態 (0: 有清單沒內容, 1: 查詢中, 2: 有內容)
        );
        ''')

        # keyword 表
        cursor.execute('''
        CREATE TABLE keyword (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 關鍵字唯一識別碼
            name VARCHAR(50) NOT NULL            -- 關鍵字名稱
        );
        ''')

        # news_keyword 表
        cursor.execute('''
        CREATE TABLE news_keyword (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_id INTEGER NOT NULL,            -- 關聯新聞 ID
            keyword_id INTEGER NOT NULL,         -- 關聯關鍵字 ID
            FOREIGN KEY(news_id) REFERENCES news(id),
            FOREIGN KEY(keyword_id) REFERENCES keyword(id)
        );
        ''')

        # category 表
        cursor.execute('''
        CREATE TABLE category (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 類別唯一識別碼
            name VARCHAR(50) NOT NULL            -- 類別名稱
        );
        ''')

        # news_category 表
        cursor.execute('''
        CREATE TABLE news_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_id INTEGER NOT NULL,            -- 關聯新聞 ID
            category_id INTEGER NOT NULL,        -- 關聯類別 ID
            FOREIGN KEY(news_id) REFERENCES news(id),
            FOREIGN KEY(category_id) REFERENCES category(id)
        );
        ''')

        # author 表
        cursor.execute('''
        CREATE TABLE author (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 作者唯一識別碼
            name VARCHAR(50) NOT NULL,           -- 作者姓名
            notes TEXT                           -- 備註
        );
        ''')

        # ai_news 表
        cursor.execute('''
        CREATE TABLE ai_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_id INTEGER NOT NULL,            -- 關聯新聞 ID
            ai_title VARCHAR(50),               -- AI 標題
            ai_sentiment_analysis VARCHAR(10),  -- AI 語意分析 (正面、負面、中立)
            ai_model VARCHAR(50),               -- AI 模型 (gemma3、llama4)
            ai_raw_content TEXT,                -- AI 原始內容
            FOREIGN KEY(news_id) REFERENCES news(id)
        );
        ''')

        # ai_news_keyword 表
        cursor.execute('''
        CREATE TABLE ai_news_keyword (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            ai_news_id INTEGER NOT NULL,         -- 關聯 AI 新聞 ID
            keyword_id INTEGER NOT NULL,         -- 關聯關鍵字 ID
            FOREIGN KEY(ai_news_id) REFERENCES ai_news(id),
            FOREIGN KEY(keyword_id) REFERENCES keyword(id)
        );
        ''')

        # ai_news_category 表
        cursor.execute('''
        CREATE TABLE ai_news_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            ai_news_id INTEGER NOT NULL,         -- 關聯 AI 新聞 ID
            category_id INTEGER NOT NULL,        -- 關聯類別 ID
            FOREIGN KEY(ai_news_id) REFERENCES ai_news(id),
            FOREIGN KEY(category_id) REFERENCES category(id)
        );
        ''')


# 資料庫連線
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def validate_required_fields(data, required_fields):
    for field in required_fields:
        if field not in data:
            return field
    return None


def check_existing_news(cursor, news_time, news_url):
    sql_query = "SELECT * FROM news WHERE news_time = ? AND news_url = ?;"
    cursor.execute(sql_query, (news_time, news_url))
    return cursor.fetchone()

def construct_insert_query(table_name, data):
    column_names = list(data.keys())
    column_values = list(data.values())
    placeholders = ", ".join(["?" for _ in column_values])
    sql_query = f"INSERT INTO {table_name} ({', '.join(column_names)}) VALUES ({placeholders});"
    return sql_query, column_values


@app.route('/news', methods=['POST'])
def add_news():
    '''
    新增多筆新聞資料到資料庫

    輸入:
        - JSON 格式的清單，每筆資料為一個新聞物件，包含以下欄位：
            - news_time (必填): 新聞發佈時間，格式為 ISO 8601 (e.g., "2025-05-29T12:00:00")
            - news_title (必填): 新聞標題，字串格式
            - news_url (必填): 新聞的網址，字串格式
            - news_content (選填): 新聞內容，字串格式
            - image_url (選填): 圖片連結，字串格式
            - source_website (選填): 來源網站，整數對應枚舉值 (e.g., 0: "台視")
            - query_state (選填): 查詢狀態，預設為 0 (0: 有清單沒內容, 1: 查詢中, 2: 有內容)

    輸出:
        - 成功狀況:
            - 狀態碼: 201
            - 回傳 JSON:
                {
                    "success": [
                        {
                            "data": <成功寫入的新聞資料>,
                            "id": <新聞資料的主鍵 ID>
                        },
                        ...
                    ],
                    "errors": [
                        {
                            "data": <有問題的新聞資料>,
                            "error": <錯誤訊息>
                        },
                        ...
                    ]
                }
        - 錯誤狀況:
            - 狀態碼: 400
            - 回傳 JSON:
                {
                    "error": "描述錯誤原因"
                }
    '''

    data_list = request.get_json()

    if not isinstance(data_list, list):
        return jsonify({'error': 'Input data should be a list of news objects'}), 400


    # 必填欄位
    required_fields = ['news_time', 'news_title', 'news_url', 'source_website']
    results = {'success': [], 'errors': []}


    with get_db_connection() as conn:
        cursor = conn.cursor()
        for data in data_list:

            # 檢查必填欄位
            missing_field = validate_required_fields(data, required_fields)
            if missing_field:
                results['errors'].append({'data': data, 'error': f'Missing required field: {missing_field}'})
                continue

            # 檢查 source_website 是否有效
            source_website = int(data.get('source_website', 0))  # 預設為 0
            if source_website not in SOURCE_WEBSITE_ENUM:
                results['errors'].append({'data': data, 'error': 'Invalid source_website value'})
                continue

            # 檢查是否已存在相同的時間和網址
            if check_existing_news(cursor, data['news_time'], data['news_url']):
                results['errors'].append({'data': data, 'error': 'News with the same time and URL already exists'})
                continue

            try:
                # 構建並執行插入查詢
                sql_query, column_values = construct_insert_query('news', data)
                cursor.execute(sql_query, column_values)
                conn.commit()

                results['success'].append({'data': data, 'id': cursor.lastrowid})
            except Exception as e:
                results['errors'].append({'data': data, 'error': str(e)})

    return jsonify(results), 201



# 修改新聞
@app.route('/news/<int:news_id>', methods=['PUT'])
def update_news(news_id):
    data = request.get_json()
    column_list = [
        'news_time', 'news_title', 'news_content', 'image_url', 'news_url',
        'source_website', 'category', 'keywords', 'author', 'ai_title', 'ai_category',
        'ai_keywords', 'ai_sentiment_analysis', 'ai_model', 'ai_raw_content', 'query_state'
    ]

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news WHERE id = ?", (news_id,))
        existing_news = cursor.fetchone()
        if not existing_news:
            return jsonify({'error': 'News not found'}), 404

        # 過濾有效欄位
        valid_data = {key: data[key] for key in column_list if key in data}
        if not valid_data:
            return jsonify({'error': 'No valid fields to update'}), 400

        # 動態生成更新的 SQL 語句
        set_clause = ', '.join([f"{key} = ?" for key in valid_data.keys()])
        update_query = f"UPDATE news SET {set_clause} WHERE id = ?"
        cursor.execute(update_query, list(valid_data.values()) + [news_id])
        conn.commit()

        return jsonify({'message': 'News updated successfully'})


# 取得待爬清單
@app.route('/get_wait_query_list', methods=['POST'])
def get_wait_query_list():
    data = request.get_json()
    source_website = int(data.get('source_website'))
    count = data.get('count')

    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql_query = """
        SELECT id, news_url
        FROM news
        WHERE query_state = 0 AND source_website = ?
        LIMIT ?;
        """
        cursor.execute(sql_query, (source_website, count))

        news_obj = cursor.fetchall()
        news_list = [news[0] for news in news_obj]  # 使用索引訪問元組中的 ID

        if news_list:  # 檢查是否有結果需要更新
            placeholders = ", ".join(["?" for _ in news_list])
            sql = f'UPDATE news SET query_state = 1 WHERE id IN ({placeholders});'
            cursor.execute(sql, news_list)
            conn.commit()

        return jsonify([{"id": news[0], "news_url": news[1]} for news in news_obj])


# 查看新聞
@app.route('/news', methods=['GET'])
def get_news():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM news')
        news_list = cursor.fetchall()
        return jsonify([dict(news) for news in news_list])



if __name__ == '__main__':
    # init_db()
    app.run(debug=True)
