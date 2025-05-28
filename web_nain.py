from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DATABASE = 'news.db'

# 初始化資料庫
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, -- 唯一識別碼
            news_time DATETIME NOT NULL,          -- 新聞時間
            news_title VARCHAR(50) NOT NULL,     -- 新聞標題
            news_content TEXT,                   -- 新聞內容
            image_url TEXT,                      -- 圖片連結
            news_url TEXT NOT NULL,              -- 新聞連結
            source_website VARCHAR(50) NOT NULL, -- 來源網站
            tags VARCHAR(100),                   -- 標籤
            author VARCHAR(50),                  -- 作者
            category VARCHAR(10),                -- AI 分類
            ai_title VARCHAR(50),                -- AI 標題
            ai_category VARCHAR(10),             -- AI 分類
            ai_keywords VARCHAR(100),            -- AI 關鍵字
            ai_sentiment_analysis VARCHAR(10),   -- AI 語意分析
            ai_model VARCHAR(50),                -- AI 模型
            ai_raw_content TEXT,                 -- AI 原始內容
            query_state INTEGER default 0        -- 查詢狀態
        );
        ''')

# 資料庫連線
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# 新增新聞
@app.route('/news', methods=['POST'])
def add_news():
    data = request.get_json()

    # 必填欄位
    required_fields = ['news_time', 'news_title', 'news_url']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # 轉換為 SQL 的時間格式
    dt_object = datetime.strptime(data['news_time'], "%Y.%m.%d %H:%M")
    data['news_time'] = dt_object.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        # 檢查是否已存在相同的時間和網址
        cursor = conn.cursor()

        sql_data = f'''SELECT * FROM news WHERE news_time = '{data['news_time']}' AND news_url = '{data["news_url"]}'; '''
        cursor.execute(sql_data)
        previous_news = cursor.fetchone()
        if previous_news:
            return jsonify({'error': 'News with the same time and URL already exists'}), 400

        column_list = [
            'news_time', 'news_title', 'news_content', 'image_url', 'news_url',
            'source_website', 'category', 'tags', 'author', 'ai_title', 'ai_category',
            'ai_keywords', 'ai_sentiment_analysis', 'ai_model', 'ai_raw_content', 'query_state'
        ]
        column_names = []
        column_values = []

        for name in column_list:
            value = data.get(name)
            if value:  # 過濾空值
                column_names.append(name)
                column_values.append(value)

        # 動態生成佔位符
        placeholders = ", ".join(["?" for _ in column_values])

        # 組建 SQL 語句
        sql_query = f'''
        INSERT INTO news ({", ".join(column_names)})
        VALUES ({placeholders});
        '''
        # 執行參數化查詢
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_query, column_values)
            conn.commit()

        cursor.execute(sql_data)
        conn.commit()
        return jsonify({'message': 'News added successfully', 'id': cursor.lastrowid}), 201

# 取得待爬清單
@app.route('/get_wait_query_list', methods=['POST'])
def get_wait_query_list():
    data = request.get_json()
    source_website = data.get('source_website')
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
        news_list = [news['id'] for news in news_obj]

        placeholders = ", ".join(["?" for _ in news_list])

        sql = f'UPDATE news SET query_state = 1 WHERE id in ({placeholders});'
        cursor.execute(sql, news_list)
        conn.commit()

        return jsonify([dict(news) for news in news_obj])


# 查看新聞
@app.route('/news', methods=['GET'])
def get_news():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM news')
        news_list = cursor.fetchall()
        return jsonify([dict(news) for news in news_list])

# 修改新聞
@app.route('/news/<int:news_id>', methods=['PUT'])
def update_news(news_id):
    data = request.get_json()
    column_list = [
        'news_time', 'news_title', 'news_content', 'image_url', 'news_url',
        'source_website', 'category', 'tags', 'author', 'ai_title', 'ai_category',
        'ai_keywords', 'ai_sentiment_analysis', 'ai_model', 'ai_raw_content', 'query_state'
    ]

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news WHERE id = ?", (news_id,))
        existing_news = cursor.fetchone()
        if not existing_news:
            return jsonify({'error': 'News not found'}), 404

        # 過濾有效欄位
        column_names = []
        column_values = []
        for name in column_list:
            if name in data:
                column_names.append(name)
                column_values.append(data[name])

        # 如果無欄位需要更新
        if not column_names:
            return jsonify({'error': 'No valid fields to update'}), 400

        # 動態生成更新的 SQL 語句
        set_clause = ', '.join([f"{col} = ?" for col in column_names])
        update_query = f"UPDATE news SET {set_clause} WHERE id = ?"
        cursor.execute(update_query, column_values + [news_id])
        conn.commit()

        return jsonify({'message': 'News updated successfully'})

if __name__ == '__main__':
    init_db()
    # app.run(debug=True)
