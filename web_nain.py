from flask import Flask, request, jsonify
import sqlite3

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
            news_content TEXT NOT NULL,          -- 新聞內容
            image_url TEXT,                      -- 圖片連結
            news_url TEXT,                       -- 新聞連結
            tags VARCHAR(100),                   -- 標籤
            author VARCHAR(50),                  -- 作者
            ai_title VARCHAR(50),                -- AI 標題
            ai_category VARCHAR(10),             -- AI 分類
            ai_keywords VARCHAR(100),            -- AI 關鍵字
            ai_sentiment_analysis VARCHAR(10),   -- AI 語意分析
            ai_model VARCHAR(50),                -- AI 模型
            ai_raw_content TEXT                  -- AI 原始內容
        );
        ''')
        conn.commit()

# 資料庫連線
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# 新增新聞
@app.route('/news', methods=['POST'])
def add_news():
    data = request.get_json()
    required_fields = ['news_time', 'news_title', 'news_content']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO news (news_time, news_title, news_content, author, news_source, ai_title, ai_category, image_url, keywords, sentiment_analysis, ai_model, ai_raw_content)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['news_time'], data['news_title'], data['news_content'],
            data.get('author'), data.get('news_source'), data.get('ai_title'),
            data.get('ai_category'), data.get('image_url'), data.get('keywords'),
            data.get('sentiment_analysis'), data.get('ai_model'), data.get('ai_raw_content')
        ))
        conn.commit()
        return jsonify({'message': 'News added successfully', 'id': cursor.lastrowid}), 201






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
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM news WHERE id = ?', (news_id,))
        existing_news = cursor.fetchone()
        if not existing_news:
            return jsonify({'error': 'News not found'}), 404

        update_fields = {
            'news_time': data.get('news_time', existing_news['news_time']),
            'news_title': data.get('news_title', existing_news['news_title']),
            'news_content': data.get('news_content', existing_news['news_content']),
            'author': data.get('author', existing_news['author']),
            'news_source': data.get('news_source', existing_news['news_source']),
            'ai_title': data.get('ai_title', existing_news['ai_title']),
            'ai_category': data.get('ai_category', existing_news['ai_category']),
            'image_url': data.get('image_url', existing_news['image_url']),
            'keywords': data.get('keywords', existing_news['keywords']),
            'sentiment_analysis': data.get('sentiment_analysis', existing_news['sentiment_analysis']),
            'ai_model': data.get('ai_model', existing_news['ai_model']),
            'ai_raw_content': data.get('ai_raw_content', existing_news['ai_raw_content']),
        }

        cursor.execute('''
        UPDATE news
        SET news_time = ?, news_title = ?, news_content = ?, author = ?, news_source = ?, ai_title = ?, ai_category = ?, image_url = ?, keywords = ?, sentiment_analysis = ?, ai_model = ?, ai_raw_content = ?
        WHERE id = ?
        ''', (
            update_fields['news_time'], update_fields['news_title'], update_fields['news_content'],
            update_fields['author'], update_fields['news_source'], update_fields['ai_title'],
            update_fields['ai_category'], update_fields['image_url'], update_fields['keywords'],
            update_fields['sentiment_analysis'], update_fields['ai_model'], update_fields['ai_raw_content'], news_id
        ))
        conn.commit()
        return jsonify({'message': 'News updated successfully'})

if __name__ == '__main__':
    # init_db()
    app.run(debug=True)
