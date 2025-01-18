from datetime import datetime
import aiosqlite
import json
from pathlib import Path
import logging

class MessageStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = None
        self.logger = logging.getLogger('WeChatBot')
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
    async def connect(self):
        """连接到数据库并确保表已创建"""
        if self.db is None:
            self.logger.debug(f"正在连接到数据库: {self.db_path}")
            self.db = await aiosqlite.connect(self.db_path)
            # 每次连接时都确保表存在
            await self._ensure_table()
        return self.db
        
    async def close(self):
        """关闭数据库连接"""
        if self.db is not None:
            self.logger.debug("正在关闭数据库连接")
            await self.db.close()
            self.db = None
            
    async def _ensure_table(self):
        """确保数据库表存在"""
        self.logger.debug("正在检查并创建数据库表")
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                group_id TEXT,
                sender_id TEXT,
                message_type TEXT,
                content TEXT,
                media_path TEXT,
                created_at TIMESTAMP,
                raw_data TEXT
            )
        ''')
        await self.db.commit()
        self.logger.debug("数据库表检查/创建完成")
            
    async def init_db(self):
        """初始化数据库（为了向后兼容）"""
        await self.connect()  # 这会自动确保表存在
            
    async def store_message(self, message_data: dict):
        """存储消息"""
        try:
            db = await self.connect()
            self.logger.debug(f"正在存储消息: {message_data['message_id']}")
            await db.execute('''
                INSERT INTO group_messages 
                (message_id, group_id, sender_id, message_type, content, media_path, created_at, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message_data['message_id'],
                message_data['group_id'],
                message_data['sender_id'],
                message_data['message_type'],
                message_data['content'],
                message_data.get('media_path'),
                datetime.now().isoformat(),
                json.dumps(message_data['raw_data'])
            ))
            await db.commit()
            self.logger.debug("消息存储成功")
        except Exception as e:
            self.logger.error(f"存储消息时发生错误: {str(e)}")
            raise

    async def store_message_to_unified_db(self, message_data: dict):
        """存储消息到统一数据库"""
        # 存储到统一数据库
        try:
            # 准备统一数据库的数据
            content = message_data['content']
            title = content[:100] + '...' if len(content) > 100 else content
            url = f"wechat://message/{message_data['message_id']}"
            
            # 假设群名映射到行业的逻辑
            industry = '电子'  # 需要根据实际情况设置行业
            
            unified_data = (
                title,                          # title
                message_data.get('processed_data') or content,  # content
                None,                           # summary
                url,                            # url
                None,                           # company_name
                None,                           # stock_code
                industry,                       # industry
                '微信群',                        # info_type
                message_data['group_id'],       # source_detail
                message_data.get('media_path'), # local_file_path
                message_data.get('created_at', datetime.now()),  # publish_time
                json.dumps(message_data.get('raw_data', {}))    # raw_data
            )
            
            async with aiosqlite.connect(str(self.unified_db_path)) as db:
                await db.execute("""
                    INSERT INTO unified_information (
                        title, content, summary, url, company_name, 
                        stock_code, industry, info_type, source_detail,
                        local_file_path, publish_time, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, unified_data)
                await db.commit()
                    
            self.logger.info(f"消息已同时存储到统一数据库")
        except Exception as e:
            self.logger.error(f"存储到统一数据库时发生错误: {e}")

    async def get_messages(self, group_id: str):
        """获取指定群组的消息"""
        db = await self.connect()
        cursor = await db.execute('SELECT * FROM group_messages WHERE group_id = ?', (group_id,))
        return await cursor.fetchall()