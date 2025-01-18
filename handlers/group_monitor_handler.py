from handlers.handlers import MessageHandler, MessageContext, ImageMessageHandler, FileMessageHandler
import logging
from pathlib import Path
from utils.message_store import MessageStore
from utils.media_downloader import MediaDownloader
from utils.bot import ChatBot  # Local import
import uuid
import asyncio
import json
import base64
import aiosqlite
import sqlite3
from datetime import datetime
import sys
sys.path.append('/home/yy/project/liujing-project-zhengquan')
from src.celery_task.tasks import llm_summary_task


class GroupMonitorHandler(MessageHandler):
    def __init__(self, config: dict):
        super().__init__()
        self.logger = logging.getLogger('WeChatBot')
        monitor_config = config.get('message_monitor', {})
        self.target_groups = monitor_config.get('target_groups', [])
        self.store = MessageStore(monitor_config.get('database', {}).get('path', 'data/message_monitor.db'))
        self.save_media = monitor_config.get('storage', {}).get('save_media', False)
        self.media_path = Path(monitor_config.get('storage', {}).get('media_path', 'data/media'))
        
        # 添加统一数据库路径
        self.unified_db_path = Path('/home/yy/project/liujing-project-zhengquan/data/unified_information.db')
        
        # 获取API配置
        wechat_config = config.get('wechat', {})
        self.api_host = wechat_config.get('base_url', 'http://localhost:2531/v2/api')
        self.app_id = wechat_config.get('app_id')  # 从wechat配置获取app_id
        self.token = wechat_config.get('token')
        
        # 初始化消息处理器
        self.image_handler = ImageMessageHandler()
        self.file_handler = FileMessageHandler()
        self.media_downloader = MediaDownloader(
            str(self.media_path),
            api_host=self.api_host,
            token=self.token
        )
        
        if self.save_media:
            self.media_path.mkdir(parents=True, exist_ok=True)
            # 创建子目录
            (self.media_path / 'images').mkdir(exist_ok=True)
            (self.media_path / 'files').mkdir(exist_ok=True)

    @classmethod
    async def create(cls, config: dict):
        """异步工厂方法创建实例"""
        instance = cls(config)
        await instance.initialize()
        return instance

    async def initialize(self):
        """异步初始化方法"""
        await self.store.init_db()

    async def can_handle(self, context: MessageContext) -> bool:
        """判断是否为目标群消息"""
        return context.from_user in self.target_groups

    async def handle(self, context: MessageContext) -> bool:
        """处理消息"""
        try:
            # 原有的消息存储
            message_data = await self._extract_message_data(context)
            await self.store.store_message(message_data)
            self.logger.info(f"已存储来自群 {message_data['group_id']} 的消息")
            
            # 存储到统一数据库并获取记录ID
            unified_id = await self.store.store_message_to_unified_db(message_data, str(self.unified_db_path))
            if unified_id:
                # 触发LLM摘要任务
                llm_summary_task.delay([unified_id])
                self.logger.info(f"已触发LLM摘要任务，记录ID: {unified_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"存储消息时发生错误: {e}")
            return False

    async def store_to_unified_db(self, message_data: dict) -> int:
        """存储消息到统一数据库并返回记录ID"""
        try:
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
                cursor = await db.execute("""
                    INSERT INTO unified_information (
                        title, content, summary, url, company_name, 
                        stock_code, industry, info_type, source_detail,
                        local_file_path, publish_time, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                """, unified_data)
                await db.commit()
                
                # 获取插入记录的ID
                row = await cursor.fetchone()
                if row:
                    return row[0]
                    
        except sqlite3.IntegrityError:
            self.logger.debug(f"消息已存在于统一数据库中，跳过")
        except Exception as e:
            self.logger.error(f"存储到统一数据库时发生错误: {e}")
        
        return None

    async def _save_media_info(self, context: MessageContext, message_id: str) -> str:
        """保存媒体信息"""
        if not self.save_media:
            return None

        try:
            if context.msg_type == 3:  # 图片消息
                # 使用 ImageMessageHandler 处理
                self.logger.debug(f"开始处理图片消息: {context.data}")
                if await self.image_handler.handle(context):
                    info_path = self.media_path / 'images' / f"{message_id}_info.json"
                    self.logger.debug(f"图片处理结果: {context.processed_data}")
                    
                    # 从processed_data中获取图片信息
                    cdn_url = context.processed_data.get('cdn_url')
                    aes_key = context.processed_data.get('aes_key')
                    
                    self.logger.debug(f"图片CDN URL: {cdn_url}")
                    self.logger.debug(f"图片AES Key: {aes_key}")
                    
                    image_info = {
                        'message_id': message_id,
                        'cdn_url': cdn_url,
                        'aes_key': aes_key
                    }
                    
                    # 保存缩略图
                    if context.img_buf:
                        self.logger.debug("开始保存缩略图")
                        thumb_path = await self.media_downloader.save_thumb(context.img_buf, message_id)
                        if thumb_path:
                            image_info['thumb_path'] = thumb_path
                            self.logger.debug(f"缩略图已保存: {thumb_path}")
                    
                    # 下载原图
                    if cdn_url and aes_key:
                        self.logger.debug("开始下载原图")
                        # 确保app_id存在
                        if not self.app_id:
                            self.logger.error("缺少必需的appId配置")
                            return None
                            
                        image_path = await self.media_downloader.download_image(
                            cdn_url,
                            aes_key,
                            message_id,
                            app_id=self.app_id,
                            xml_content=context.content
                        )
                        if image_path:
                            image_info['image_path'] = image_path
                            self.logger.debug(f"原图已保存: {image_path}")
                    else:
                        self.logger.warning("缺少图片CDN URL或AES Key，无法下载原图")
                    
                    info_path.write_text(json.dumps(image_info, indent=2, ensure_ascii=False))
                    return str(info_path)
                else:
                    self.logger.error("图片消息处理失败")
                    
            elif context.msg_type == 49:  # 文件消息
                # 使用 FileMessageHandler 处理
                if await self.file_handler.handle(context):
                    info_path = self.media_path / 'files' / f"{message_id}_info.json"
                    file_info = {
                        'message_id': message_id,
                        **context.processed_data  # 包含所有处理后的文件信息
                    }
                    
                    # 下载文件
                    if file_info.get('cdn_url') and file_info.get('aes_key'):
                        # 确保app_id存在
                        if not self.app_id:
                            self.logger.error("缺少必需的appId配置")
                            return None
                            
                        file_name = f"{message_id}_{file_info['file_name']}"
                        if file_info.get('file_ext'):
                            file_name = f"{file_name}.{file_info['file_ext']}"
                            
                        file_path = await self.media_downloader.download_file(
                            file_info['cdn_url'],
                            file_info['aes_key'],
                            file_name,
                            app_id=self.app_id,
                            xml_content=context.content
                        )
                        if file_path:
                            file_info['file_path'] = file_path
                    
                    info_path.write_text(json.dumps(file_info, indent=2, ensure_ascii=False))
                    return str(info_path)
                    
        except Exception as e:
            self.logger.error(f"保存媒体信息失败: {e}")
            self.logger.error(f"消息内容: {context.content}")
            self.logger.error(f"消息数据: {context.data}")
        return None

    async def _extract_message_data(self, context: MessageContext) -> dict:
        """提取消息数据"""
        message_id = str(uuid.uuid4())  # 生成唯一消息ID
        message_type = context.type_name
        group_id = context.from_user
        sender_id = context.data.get('FromUserName', {}).get('string', '')
        content = context.content
        media_path = None
        
        # 处理媒体消息
        if context.msg_type == 3:  # 图片消息
            try:
                import xml.etree.ElementTree as ET
                xml_content = context.content
                
                # 处理可能存在的发送者ID前缀
                if ':' in xml_content:
                    xml_content = xml_content.split(':', 1)[1].strip()
                
                root = ET.fromstring(xml_content)
                img_node = root.find('img')
                
                if img_node is not None:
                    # 获取图片信息
                    cdn_url = img_node.get('cdnthumburl')
                    aes_key = img_node.get('cdnthumbaeskey')
                    
                    # 更新context的processed_data
                    context.processed_data = {
                        'cdn_url': cdn_url,
                        'aes_key': aes_key
                    }
                    
                    self.logger.debug(f"解析到图片信息: cdn_url={cdn_url}, aes_key={aes_key}")
                    # 传递原始XML内容
                    context.content = xml_content
                    media_path = await self._save_media_info(context, message_id)
                    if media_path:
                        self.logger.info(f"图片信息已保存到: {media_path}")
                else:
                    self.logger.error("未找到图片节点")
            except Exception as e:
                self.logger.error(f"解析图片XML失败: {e}")
                self.logger.error(f"XML内容: {content}")
        elif context.msg_type == 49:  # appmsg消息
            try:
                import xml.etree.ElementTree as ET
                xml_content = context.content
                
                # 处理可能存在的发送者ID前缀
                if ':' in xml_content:
                    xml_content = xml_content.split(':', 1)[1].strip()
                
                root = ET.fromstring(xml_content)
                appmsg = root.find('appmsg')
                
                if appmsg is not None:
                    msg_type = int(appmsg.find('type').text)
                    title = appmsg.find('title').text
                    
                    # 更新消息类型
                    if msg_type == 5:  # 链接卡片
                        message_type = 'link'
                        url = appmsg.find('url').text
                        des = appmsg.find('des').text
                        thumb_url = appmsg.find('thumburl').text
                        
                        # 添加链接相关信息
                        context.processed_data = {
                            'title': title,
                            'description': des,
                            'url': url,
                            'thumb_url': thumb_url
                        }
                        self.logger.info(f"解析到链接卡片: {title} - {url}")
                        
                    elif msg_type == 6:  # 文件消息
                        message_type = 'file'
                        appattach = appmsg.find('appattach')
                        if appattach is not None:
                            file_ext = appattach.find('fileext').text
                            file_size = int(appattach.find('totallen').text)
                            cdn_url = appattach.find('cdnattachurl').text
                            aes_key = appattach.find('aeskey').text
                            
                            # 更新context的processed_data
                            context.processed_data = {
                                'file_name': title,
                                'file_ext': file_ext,
                                'file_size': file_size,
                                'cdn_url': cdn_url,
                                'aes_key': aes_key
                            }
                            self.logger.info(f"解析到文件消息: {title}.{file_ext}, 大小: {file_size}字节")
                            # 传递原始XML内容
                            context.content = xml_content
                            media_path = await self._save_media_info(context, message_id)
                            if media_path:
                                self.logger.info(f"文件信息已保存到: {media_path}")
                    else:
                        self.logger.warning(f"未处理的appmsg类型: {msg_type}")
                else:
                    self.logger.error("未找到appmsg节点")
            except Exception as e:
                self.logger.error(f"解析appmsg XML失败: {e}")
                self.logger.error(f"XML内容: {content}")
        
        message_data = {
            'message_id': message_id,
            'group_id': group_id,
            'sender_id': sender_id,
            'message_type': message_type,
            'content': content,
            'media_path': media_path,
            'raw_data': context.data
        }
        
        # 如果有processed_data，添加到message_data中
        if hasattr(context, 'processed_data') and context.processed_data:
            message_data['processed_data'] = context.processed_data

        return message_data