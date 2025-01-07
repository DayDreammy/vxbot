import aiosqlite
import json

class MessageStore:
    """消息存储类"""
    
    def __init__(self, db_path: str = 'data/message_monitor.db'):
        self.db_path = db_path
    
    async def init_db(self):
        """初始化数据库"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                group_id TEXT,
                sender_id TEXT,
                message_type TEXT,
                content TEXT,
                media_path TEXT,
                processed_data TEXT,
                created_at TIMESTAMP,
                raw_data TEXT
            )
            """)
            await db.commit()
            
    async def store_message(self, message_data: dict):
        """存储消息"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            INSERT INTO group_messages 
            (message_id, group_id, sender_id, message_type, content, media_path, processed_data, created_at, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            """, (
                message_data['message_id'],
                message_data['group_id'],
                message_data['sender_id'],
                message_data['message_type'],
                message_data['content'],
                message_data.get('media_path'),
                json.dumps(message_data.get('processed_data')) if message_data.get('processed_data') else None,
                json.dumps(message_data.get('raw_data'))
            )) 