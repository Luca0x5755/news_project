from flask import Flask, request, jsonify
import sqlite3
import traceback

app = Flask(__name__)
DATABASE = 'news.db'

SOURCE_WEBSITE_ENUM = {
    1: "台視",
}

SENTIMENT_ANALYSIS_ENUM = {
    0: "中立",
    1: "正面",
    2: "負面",
}

AI_MODEL_ENUM = {
    1: "gemma3:12b-it-qat",
}


# 初始化資料庫
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        # author 表
        cursor.execute('''
        CREATE TABLE author (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 作者唯一識別碼
            name VARCHAR(50) NOT NULL,            -- 作者姓名
            notes TEXT                            -- 備註
        );
        ''')

        # news 表
        cursor.execute('''
        CREATE TABLE news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_time DATETIME NOT NULL,          -- 新聞時間
            news_title VARCHAR(50) NOT NULL,      -- 新聞標題
            news_content TEXT,                    -- 新聞內容
            image_url TEXT,                       -- 圖片連結
            news_url TEXT NOT NULL,               -- 新聞連結
            source_website INTEGER NOT NULL,      -- 來源網站
            author_id INTEGER,                    -- 作者
            query_state INTEGER DEFAULT 0,        -- 查詢狀態 (0: 有清單沒內容, 1: 查詢中, 2: 有內容)
            FOREIGN KEY(author_id) REFERENCES author(id)
        );
        ''')

        # keyword 表
        cursor.execute('''
        CREATE TABLE keyword (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 關鍵字唯一識別碼
            name VARCHAR(50) NOT NULL             -- 關鍵字名稱
        );
        ''')

        # news_keyword 表
        cursor.execute('''
        CREATE TABLE news_keyword (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_id INTEGER NOT NULL,             -- 關聯新聞 ID
            keyword_id INTEGER NOT NULL,          -- 關聯關鍵字 ID
            FOREIGN KEY(news_id) REFERENCES news(id),
            FOREIGN KEY(keyword_id) REFERENCES keyword(id)
        );
        ''')

        # category 表
        cursor.execute('''
        CREATE TABLE category (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 類別唯一識別碼
            name VARCHAR(50) NOT NULL             -- 類別名稱
        );
        ''')

        # news_category 表
        cursor.execute('''
        CREATE TABLE news_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_id INTEGER NOT NULL,             -- 關聯新聞 ID
            category_id INTEGER NOT NULL,         -- 關聯類別 ID
            FOREIGN KEY(news_id) REFERENCES news(id),
            FOREIGN KEY(category_id) REFERENCES category(id)
        );
        ''')

        # ai_news 表
        cursor.execute('''
        CREATE TABLE ai_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,    -- 唯一識別碼
            news_id INTEGER NOT NULL,                -- 關聯新聞 ID
            ai_title VARCHAR(50),                    -- AI 標題
            ai_sentiment_analysis INTEGER NOT NULL,  -- AI 語意分析 (0:中立、1:正面、2:負面)
            ai_model INTEGER NOT NULL,               -- AI 模型 (1:gemma3:12b-it-qat、)
            FOREIGN KEY(news_id) REFERENCES news(id)
        );
        ''')

        # ai_news_keyword 表
        cursor.execute('''
        CREATE TABLE ai_news_keyword (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            ai_news_id INTEGER NOT NULL,          -- 關聯 AI 新聞 ID
            keyword_id INTEGER NOT NULL,          -- 關聯關鍵字 ID
            FOREIGN KEY(ai_news_id) REFERENCES ai_news(id),
            FOREIGN KEY(keyword_id) REFERENCES keyword(id)
        );
        ''')

        # ai_news_category 表
        cursor.execute('''
        CREATE TABLE ai_news_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            ai_news_id INTEGER NOT NULL,          -- 關聯 AI 新聞 ID
            category_id INTEGER NOT NULL,         -- 關聯類別 ID
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

# 新增新聞
@app.route('/news', methods=['POST'])
def add_news():
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

# 更新新聞
@app.route('/news/<int:news_id>', methods=['PUT'])
def update_news(news_id):
    data = request.get_json()
    column_list = [
        'news_time', 'news_title', 'news_content', 'image_url',
        'news_url', 'source_website', 'query_state'
    ]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 檢查是否存在指定 ID 的新聞
        cursor.execute("SELECT * FROM news WHERE id = ?", (news_id,))
        existing_news = cursor.fetchone()
        if not existing_news:
            return jsonify({'error': 'News not found'}), 404

        # 過濾有效欄位
        valid_data = {key: data[key] for key in column_list if key in data}
        if not valid_data and 'keywords' not in data and 'category' not in data:
            return jsonify({'error': 'No valid fields to update'}), 400

        # 檢查 source_website 是否有效
        if 'source_website' in valid_data:
            if valid_data['source_website'] not in SOURCE_WEBSITE_ENUM:
                return jsonify({'error': 'Invalid source_website value'}), 400

        if 'author' in data:
            cursor.execute("SELECT id FROM author WHERE name = ?", (data['author'],))
            author_record = cursor.fetchone()
            if not author_record:
                cursor.execute("INSERT INTO author (name) VALUES (?)", (data['author'],))
                conn.commit()
                author_id = cursor.lastrowid
            else:
                author_id = author_record['id']
            valid_data['author_id'] = author_id

        # 更新 news 表資料
        if valid_data:
            set_clause = ', '.join([f"{key} = ?" for key in valid_data.keys()])
            update_query = f"UPDATE news SET {set_clause} WHERE id = ?"
            cursor.execute(update_query, list(valid_data.values()) + [news_id])
            conn.commit()

        # 新增 keywords 並與 news_keyword 關聯
        if 'keywords' in data:
            for keyword in data['keywords']:
                # 檢查 keyword 是否已存在
                cursor.execute("SELECT id FROM keyword WHERE name = ?", (keyword,))
                keyword_record = cursor.fetchone()
                if not keyword_record:
                    cursor.execute("INSERT INTO keyword (name) VALUES (?)", (keyword,))
                    conn.commit()
                    keyword_id = cursor.lastrowid
                else:
                    keyword_id = keyword_record['id']

                # 建立 news_keyword 關聯
                cursor.execute("SELECT * FROM news_keyword WHERE news_id = ? AND keyword_id = ?", (news_id, keyword_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO news_keyword (news_id, keyword_id) VALUES (?, ?)", (news_id, keyword_id))
                    conn.commit()

        # 新增 category 並與 news_category 關聯
        if 'category' in data:
            for category in data['category']:
                # 檢查 category 是否已存在
                cursor.execute("SELECT id FROM category WHERE name = ?", (category,))
                category_record = cursor.fetchone()
                if not category_record:
                    cursor.execute("INSERT INTO category (name) VALUES (?)", (category,))
                    conn.commit()
                    category_id = cursor.lastrowid
                else:
                    category_id = category_record['id']

                # 建立 news_category 關聯
                cursor.execute("SELECT * FROM news_category WHERE news_id = ? AND category_id = ?", (news_id, category_id))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO news_category (news_id, category_id) VALUES (?, ?)", (news_id, category_id))
                    conn.commit()

        return jsonify({'message': 'News updated successfully'}), 200

# 取得代查詢清單
@app.route('/wait_query_list', methods=['POST'])
def wait_query_list():
    data = request.get_json()

    try:
        source_website = int(data.get('source_website'))
        count = int(data.get('count'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid source_website or count'}), 400

    if source_website not in SOURCE_WEBSITE_ENUM:
        return jsonify({'error': 'Invalid source_website value'}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 查詢待爬清單
        sql_query = """
        SELECT id, news_url
        FROM news
        WHERE query_state = 0 AND source_website = ?
        LIMIT ?;
        """
        cursor.execute(sql_query, (source_website, count))
        news_obj = cursor.fetchall()

        # 更新 query_state 為 1
        if news_obj:
            news_ids = [news['id'] for news in news_obj]
            placeholders = ", ".join(["?" for _ in news_ids])
            update_query = f"UPDATE news SET query_state = 1 WHERE id IN ({placeholders});"
            cursor.execute(update_query, news_ids)
            conn.commit()

        # 返回待爬清單
        news_list = [{"id": news["id"], "news_url": news["news_url"]} for news in news_obj]
        return jsonify(news_list), 200

# 需要ai處理的新聞
@app.route('/wait_ai_handle_list', methods=['post'])
def wait_ai_handle_list():
    data = request.get_json()
    count = int(data.get('count'))

    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql_query = '''
            SELECT news.id id, news.news_content news_content
            FROM news
            LEFT JOIN ai_news ON news.id = ai_news.news_id
            WHERE news.query_state = 2 AND ai_news.news_id IS NULL
            LIMIT ?;
        '''
        cursor.execute(sql_query, (count,))
        news_list = cursor.fetchall()
        return jsonify([dict(news) for news in news_list])

# 寫入AI新聞
@app.route('/add_ai_news', methods=['POST'])
def add_ai_news():
    try:
        data = request.get_json()

        # 取得資料
        title = data.get('title')
        categories = data.get('category', [])
        keywords = data.get('keyword', [])
        sentiment_analysis = data.get('sentiment_analysis')
        news_id = int(data.get('news_id'))

        # 驗證資料
        if not title or not categories or not keywords or sentiment_analysis not in SENTIMENT_ANALYSIS_ENUM.values() or not news_id:
            return jsonify({"error": "Invalid data"}), 400

        # 連接資料庫
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 新增 ai_news
            sentiment_analysis_key = next(key for key, value in SENTIMENT_ANALYSIS_ENUM.items() if value == sentiment_analysis)
            ai_model_key = next(iter(AI_MODEL_ENUM))  # 預設使用第一個 AI 模型

            cursor.execute('''
            INSERT INTO ai_news (news_id, ai_title, ai_sentiment_analysis, ai_model)
            VALUES (?, ?, ?, ?)
            ''', (news_id, title, sentiment_analysis_key, ai_model_key))

            conn.commit()
            ai_news_id = cursor.lastrowid

            # 新增 category 並與 ai_news_category 關聯
            for category in categories:
                # 檢查 category 是否已存在
                cursor.execute("SELECT id FROM category WHERE name = ?", (category,))
                category_record = cursor.fetchone()

                if not category_record:
                    cursor.execute("INSERT INTO category (name) VALUES (?)", (category,))
                    category_id = cursor.lastrowid
                else:
                    category_id = category_record['id']

                # 建立 ai_news_category 關聯
                cursor.execute("INSERT INTO ai_news_category (ai_news_id, category_id) VALUES (?, ?)", (ai_news_id, category_id))

            # 新增 keywords 並與 ai_news_keyword 關聯
            for keyword in keywords:
                # 檢查 keyword 是否已存在
                cursor.execute("SELECT id FROM keyword WHERE name = ?", (keyword,))
                keyword_record = cursor.fetchone()

                if not keyword_record:
                    cursor.execute("INSERT INTO keyword (name) VALUES (?)", (keyword,))
                    keyword_id = cursor.lastrowid
                else:
                    keyword_id = keyword_record['id']

                cursor.execute("INSERT INTO ai_news_keyword (ai_news_id, keyword_id) VALUES (?, ?)", (ai_news_id, keyword_id))

            # 所有操作完成後手動提交
            conn.commit()

        return jsonify({"message": "AI news added successfully"}), 201

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # init_db()
    app.run()# debug=True
