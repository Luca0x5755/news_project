from flask import Flask, request, jsonify, render_template
import sqlite3
import traceback
from configparser import ConfigParser

app = Flask(__name__)
DATABASE = 'news.db'

SOURCE_WEBSITE_ENUM = {
    1: "台視",
    2: "三立"
}

SENTIMENT_ANALYSIS_ENUM = {
    0: "中立",
    1: "正面",
    2: "負面",
}

AI_MODEL_ENUM = {
    1: "gemma3:12b-it-qat",
    2: "gemma3:4b-it-qat",
}

reversed_AI_MODEL_ENUM = {v: k for k, v in AI_MODEL_ENUM.items()}

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
    """
    輸入：無
    輸出：sqlite3 資料庫連線物件
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def validate_required_fields(data, required_fields):
    """
    輸入：data (dict), required_fields (list)
    輸出：缺少欄位名稱 (str) 或 None
    """
    for field in required_fields:
        if field not in data:
            return field
    return None

def check_existing_news_batch(cursor, news_items):
    """
    輸入：cursor, news_items (list of dict)
    輸出：set，存在於資料庫中的 (news_time, news_url) tuple
    """
    placeholders = ', '.join(['(?, ?)'] * len(news_items))
    values = [(item['news_time'], item['news_url']) for item in news_items]
    flat_values = [v for pair in values for v in pair]
    sql = f"SELECT news_time, news_url FROM news WHERE (news_time, news_url) IN ({placeholders})"
    cursor.execute(sql, flat_values)
    return set((row['news_time'], row['news_url']) for row in cursor.fetchall())

def construct_insert_query(table_name, data_sample):
    """
    輸入：table_name (str), data_sample (dict)
    輸出：SQL 語句 (str), 欄位名稱 (list)
    """
    columns = list(data_sample.keys())
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    return sql, columns

def get_or_create(cursor, table, name):
    """
    輸入：cursor, table (str), name (str)
    輸出：資料表對應的 id (int)，若不存在則新增
    """

    cursor.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
    record = cursor.fetchone()
    if record:
        return record['id']
    cursor.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return cursor.lastrowid

def update_relations(cursor, relation_table, news_id, entity_table, names):
    """
    輸入：cursor, relation_table (str), news_id (int), entity_table (str), names (list of str)
    輸出：無，建立關聯並避免重複
    """
    for name in names:
        entity_id = get_or_create(cursor, entity_table, name)
        cursor.execute(
            f"SELECT 1 FROM {relation_table} WHERE news_id = ? AND {entity_table}_id = ?",
            (news_id, entity_id)
        )
        if not cursor.fetchone():
            cursor.execute(
                f"INSERT INTO {relation_table} (news_id, {entity_table}_id) VALUES (?, ?)",
                (news_id, entity_id)
            )

def get_news_by_id(cursor, news_id):
    """
    輸入：cursor, news_id (int)
    輸出：對應新聞記錄或 None
    """
    cursor.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    return cursor.fetchone()

def update_news_record(cursor, news_id, data, allowed_fields):
    """
    輸入：cursor, news_id (int), data (dict), allowed_fields (list of str)
    輸出：無，更新資料
    """
    valid_data = {key: data[key] for key in allowed_fields if key in data}
    if 'source_website' in valid_data and valid_data['source_website'] not in SOURCE_WEBSITE_ENUM:
        raise ValueError('Invalid source_website value')

    if 'author' in data and data['author']:
        author_id = get_or_create(cursor, 'author', data['author'])
        valid_data['author_id'] = author_id

    if valid_data:
        set_clause = ', '.join([f"{key} = ?" for key in valid_data.keys()])
        query = f"UPDATE news SET {set_clause} WHERE id = ?"
        cursor.execute(query, list(valid_data.values()) + [news_id])

def fetch_waiting_news(cursor, source_website, count):
    """
    輸入：cursor、source_website (int)、count (int)
    輸出：查詢到待處理新聞 (list of Row)
    """
    query = """
        SELECT id, news_url
        FROM news
        WHERE query_state = 0 AND source_website = ?
        LIMIT ?;
    """
    cursor.execute(query, (source_website, count))
    return cursor.fetchall()

def mark_news_as_in_query(cursor, news_ids):
    """
    輸入：cursor、news_ids (list of int)
    輸出：無；批次更新 query_state 為 1
    """
    if not news_ids:
        return
    placeholder = ", ".join(["?"] * len(news_ids))
    query = f"UPDATE news SET query_state = 1 WHERE id IN ({placeholder});"
    cursor.execute(query, news_ids)

def fetch_waiting_ai_news(cursor, count, model):
    """
    輸入：cursor、count (int)、model(int)
    輸出：查詢到尚未經 AI 處理之新聞內容 (list of dict)
    """
    query = '''
        SELECT *
        FROM news
        LEFT JOIN ai_news ON ai_news.ai_model = ? and news.id = ai_news.news_id
        WHERE news.query_state = 2 AND ai_news.ai_model IS NULL
        LIMIT ?;
    '''
    cursor.execute(query, (model, count))
    return cursor.fetchall()

def get_or_create_ids(cursor, table, names):
    """
    輸入：table: str, names: list[str]
    輸出：對應名稱在資料表中的 id list[int]
    """
    ids = []
    for name in names:
        cursor.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
        record = cursor.fetchone()
        if not record:
            cursor.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
            ids.append(cursor.lastrowid)
        else:
            ids.append(record["id"])
    return ids

def insert_relations(cursor, relation_table, foreign_key1, foreign_key2, id1, ids2):
    """
    輸入：
        relation_table: 關聯表名稱
        foreign_key1: 主表外鍵名稱
        foreign_key2: 關聯表外鍵名稱
        id1: 主表 id
        ids2: 關聯表多個 id
    功能：建立多筆關聯
    """
    relation_data = [(id1, id2) for id2 in ids2]
    cursor.executemany(
        f"INSERT INTO {relation_table} ({foreign_key1}, {foreign_key2}) VALUES (?, ?)",
        relation_data
    )

def get_sentiment_analysis_key(value):
    """
    輸入：中文 sentiment value
    輸出：對應 ENUM key，若無則回傳 None
    """
    for k, v in SENTIMENT_ANALYSIS_ENUM.items():
        if v == value:
            return k
    return None


@app.route('/news', methods=['POST'])
def add_news():
    """
    輸入：POST 請求 (list of news objects)
    輸出：JSON 結果，包含 success 與 errors
    """
    data_list = request.get_json()
    if not isinstance(data_list, list):
        return jsonify({'error': 'Input should be a list of news objects'}), 400

    required_fields = ['news_time', 'news_title', 'news_url', 'source_website']
    results = {'success': [], 'errors': []}

    with get_db_connection() as conn:
        cursor = conn.cursor()

        insert_data = []
        for data in data_list:
            # 檢查必要欄位
            for field in required_fields:
                if not data.get(field):
                    results['errors'].append({'data': data, 'error': f'Missing field: {field}'})
                    break
            else:
                # 檢查網站來源是否合法
                try:
                    source_website = int(data['source_website'])
                    if source_website not in SOURCE_WEBSITE_ENUM:
                        raise ValueError()
                except Exception:
                    results['errors'].append({'data': data, 'error': 'Invalid source_website'})
                    continue

                insert_data.append(data)

        if not insert_data:
            return jsonify(results), 400

        # 檢查是否有重複的資料
        existing_keys = check_existing_news_batch(cursor, insert_data)

        final_data = []
        for data in insert_data:
            key = (data['news_time'], data['news_url'])
            if key in existing_keys:
                results['errors'].append({'data': data, 'error': 'Duplicate news (same time and URL)'})
                continue
            final_data.append(data)

        # 寫入資料庫
        for data in final_data:
            try:
                # author 處理
                author_id = None
                if 'author' in data:
                    if data['author']:
                        author_id = get_or_create(cursor, 'author', data['author'])
                        data['author_id'] = author_id

                # category 處理（單筆字串）
                category_id = None
                if 'category' in data and data['category']:
                    cursor.execute("SELECT id FROM category WHERE name = ?", (data['category'],))
                    category = cursor.fetchone()
                    if not category:
                        cursor.execute("INSERT INTO category (name) VALUES (?)", (data['category'],))
                        category_id = cursor.lastrowid
                    else:
                        category_id = category['id']

                # 想取出的 keys
                keys_to_extract = ['news_title', 'news_content', 'image_url', 'query_state', 'news_url', 'source_website', 'news_time', 'author_id']
                # 建立新的 dict
                new_dict = {k: data[k] for k in keys_to_extract if k in data}

                # 組合插入欄位與 SQL
                insert_sql, column_names = construct_insert_query('news', new_dict)
                values = tuple(data.get(col) for col in column_names)

                cursor.execute(insert_sql, values)
                news_id = cursor.lastrowid

                # 新增 category 關聯
                if category_id:
                    cursor.execute("INSERT INTO news_category (news_id, category_id) VALUES (?, ?)", (news_id, category_id))

                # 新增 keyword 關聯
                if 'keywords' in data and isinstance(data['keywords'], list):
                    for keyword in data['keywords']:
                        cursor.execute("SELECT id FROM keyword WHERE name = ?", (keyword,))
                        kw = cursor.fetchone()
                        if not kw:
                            cursor.execute("INSERT INTO keyword (name) VALUES (?)", (keyword,))
                            keyword_id = cursor.lastrowid
                        else:
                            keyword_id = kw['id']
                        cursor.execute("INSERT INTO news_keyword (news_id, keyword_id) VALUES (?, ?)", (news_id, keyword_id))

                results['success'].append({'data': data, 'id': news_id})
                conn.commit()
            except Exception as e:
                conn.rollback()
                results['errors'].append({'data': data, 'error': str(e)})
                traceback.print_exc()

    return jsonify(results), 201

@app.route('/news/<int:news_id>', methods=['PUT'])
def update_news(news_id):
    """
    輸入：PUT 請求（news_id 路由參數，body 為 JSON）
    輸出：更新成功訊息或錯誤回應（JSON）
    """
    data = request.get_json()
    allowed_fields = [
        'news_time', 'news_title', 'news_content', 'image_url',
        'news_url', 'source_website', 'query_state'
    ]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 檢查新聞是否存在
        if not get_news_by_id(cursor, news_id):
            return jsonify({'error': 'News not found'}), 404

        try:
            update_news_record(cursor, news_id, data, allowed_fields)

            if 'keywords' in data:
                update_relations(cursor, 'news_keyword', news_id, 'keyword', data['keywords'])

            if 'category' in data:
                update_relations(cursor, 'news_category', news_id, 'category', data['category'])

            conn.commit()
            return jsonify({'message': 'News updated successfully'}), 200
        except ValueError as ve:
            traceback.print_exc()
            return jsonify({'error': str(ve)}), 400

        except Exception as e:
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

@app.route('/wait_query_list', methods=['POST'])
def wait_query_list():
    """
    輸入：JSON {source_website: int, count: int}
    輸出：[{id: int, news_url: str}, ...]
    """
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
        news_rows = fetch_waiting_news(cursor, source_website, count)

        # 更新 query_state 為 1
        news_ids = [row['id'] for row in news_rows]
        mark_news_as_in_query(cursor, news_ids)
        conn.commit()

        news_list = [{'id': row['id'], 'news_url': row['news_url']} for row in news_rows]
        return jsonify(news_list), 200

@app.route('/wait_ai_handle_list', methods=['POST'])
def wait_ai_handle_list():
    """
    輸入：JSON {count: int, model: str}
    輸出：[{id: int, news_content: str}, ...]
    """
    data = request.get_json()
    try:
        count = int(data.get('count'))
        model = reversed_AI_MODEL_ENUM[data.get('model')]

    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid count'}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        news_rows = fetch_waiting_ai_news(cursor, count, model)
        return jsonify([dict(row) for row in news_rows]), 200

@app.route('/add_ai_news', methods=['POST'])
def add_ai_news():
    """
    輸入：JSON {
        title: str,
        category: list[str],
        keyword: list[str],
        sentiment_analysis: str,
        news_id: int,
        model: str
    }
    輸出：201 + 新增成功訊息 或 400/500 錯誤
    """
    try:
        data = request.get_json()

        # 取得資料與驗證
        title = data.get('title')
        categories = data.get('category', [])
        keywords = data.get('keyword', [])
        sentiment_val = data.get('sentiment_analysis')
        news_id = data.get('news_id')
        model = reversed_AI_MODEL_ENUM[data.get('model')]


        sentiment_key = get_sentiment_analysis_key(sentiment_val)
        if not (title and categories and keywords and sentiment_key is not None and isinstance(news_id, int)):
            return jsonify({"error": "Invalid data"}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 建立 ai_news 主表資料
            cursor.execute(
                '''
                INSERT INTO ai_news (news_id, ai_title, ai_sentiment_analysis, ai_model)
                VALUES (?, ?, ?, ?)
                ''',
                (news_id, title, sentiment_key, model)
            )
            ai_news_id = cursor.lastrowid

            # 類別與關聯
            category_ids = get_or_create_ids(cursor, "category", categories)
            insert_relations(cursor, "ai_news_category", "ai_news_id", "category_id", ai_news_id, category_ids)

            # 關鍵字與關聯
            keyword_ids = get_or_create_ids(cursor, "keyword", keywords)
            insert_relations(cursor, "ai_news_keyword", "ai_news_id", "keyword_id", ai_news_id, keyword_ids)

            conn.commit()

        return jsonify({"message": "AI news added successfully"}), 201

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return render_template('news.html')

def main():
    config = ConfigParser()
    config.read('config.ini')

    host = config['WEB_SERVER']['host']
    port = int(config['WEB_SERVER']['port'])

    app.run(debug=True, host=host, port=port)

if __name__ == '__main__':
    # init_db()
    main()
