import asyncio
from abc import ABC, abstractmethod
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
import logging
import json


class MessageContext:
    """消息上下文，包含消息的所有相关信息"""

    def __init__(self, raw_message: Dict[str, Any]):
        self.raw_message = raw_message
        self.type_name = raw_message.get('TypeName')
        self.app_id = raw_message.get('Appid')
        self.wxid = raw_message.get('Wxid')
        self.data = raw_message.get('Data', {})

        # 解析常用的消息字段
        self.msg_type = self.data.get('MsgType')
        self.from_user = self.data.get('FromUserName', {}).get('string')
        self.to_user = self.data.get('ToUserName', {}).get('string')
        self.content = self.data.get('Content', {}).get('string')
        self.create_time = self.data.get('CreateTime')

        # 图片消息特有字段
        self.img_buf = self.data.get('ImgBuf', {}).get('buffer')

        # 解析XML内容（适用于图片和文件消息）
        self.xml_content = None
        if self.content and (self.msg_type in [3, 49]):
            try:
                # 处理群消息内容
                xml_text = self.content
                if ':\n' in xml_text:  # 群消息格式
                    xml_text = xml_text.split(':\n', 1)[1]  # 获取实际的XML内容
                self.xml_content = ET.fromstring(xml_text)
            except ET.ParseError:
                self.xml_content = None

        # 用于存储处理过程中的中间数据
        self.processed_data = {}


class MessageHandler(ABC):
    """消息处理器基类"""

    def __init__(self):
        self.next_handlers: List[MessageHandler] = []
        self.logger = logging.getLogger('WeChatBot')
        self.processing_complete = False  # 标记处理器的处理状态

    def add_handler(self, handler: 'MessageHandler') -> 'MessageHandler':
        """添加下一级处理器"""
        self.next_handlers.append(handler)
        return handler

    @abstractmethod
    async def can_handle(self, context: MessageContext) -> bool:
        """判断是否可以处理该消息"""
        pass

    @abstractmethod
    async def handle(self, context: MessageContext) -> bool:
        """处理消息"""
        pass

    async def process(self, context: MessageContext) -> bool:
        """处理消息并传递给下一级处理器"""
        self.processing_complete = False
        handler_success = False

        # 检查是否可以处理该消息
        if await self.can_handle(context):
            # 执行当前处理器的处理逻辑
            handler_success = await self.handle(context)

        # 如果有子处理器，等待所有子处理器完成处理
        if self.next_handlers:
            tasks = [handler.process(context) for handler in self.next_handlers]
            sub_results = await asyncio.gather(*tasks)

            # 检查所有子处理器的处理状态
            all_complete = all(handler.processing_complete for handler in self.next_handlers)
            if all_complete:
                self.processing_complete = True
                self.logger.debug(f"处理器 {self.__class__.__name__} 的所有子处理器已完成处理")
        else:
            # 如果没有子处理器，则当前处理器完成处理
            self.processing_complete = True
            self.logger.debug(f"叶子处理器 {self.__class__.__name__} 完成处理")

        return handler_success


class TextMessageHandler(MessageHandler):
    """文本消息处理器"""

    async def can_handle(self, context: MessageContext) -> bool:
        return context.msg_type == 1

    async def handle(self, context: MessageContext) -> bool:
        self.logger.info(f"收到文本消息 - 来自: {context.from_user}, 内容: {context.content}")
        return True


class ImageMessageHandler(MessageHandler):
    """图片消息处理器"""

    async def can_handle(self, context: MessageContext) -> bool:
        return context.msg_type == 3

    async def handle(self, context: MessageContext) -> bool:
        if context.xml_content is None:
            self.logger.error("图片消息XML解析失败")
            return False

        img_element = context.xml_content.find('.//img')
        if img_element is not None:
            cdn_url = img_element.get('cdnthumburl', '')
            aes_key = img_element.get('aeskey', '')
            self.logger.info(f"收到图片消息 - 来自: {context.from_user}")
            self.logger.debug(f"图片CDN URL: {cdn_url}")
            self.logger.debug(f"图片AES Key: {aes_key}")

            if context.img_buf:
                self.logger.info("收到图片缩略图数据")

            context.processed_data['cdn_url'] = cdn_url
            context.processed_data['aes_key'] = aes_key
            return True

        self.logger.error("图片消息缺少必要的信息")
        return False


class FileMessageHandler(MessageHandler):
    """文件消息处理器"""

    async def can_handle(self, context: MessageContext) -> bool:
        return context.msg_type == 49

    async def handle(self, context: MessageContext) -> bool:
        # 添加原始消息内容的日志
        self.logger.info(f"原始消息数据: {json.dumps(context.data, ensure_ascii=False, indent=2)}")
        self.logger.info(f"消息内容: {context.content}")
        
        if context.xml_content is None:
            self.logger.error("文件消息XML解析失败")
            return False

        # 添加XML内容的日志
        # self.logger.info(f"XML内容: {ET.tostring(context.xml_content, encoding='unicode')}")

        appmsg = context.xml_content.find('.//appmsg')
        if appmsg is not None:
            # 添加appmsg内容的日志
            # self.logger.info(f"appmsg内容: {ET.tostring(appmsg, encoding='unicode')}")
            
            msg_type = appmsg.find('type').text if appmsg.find('type') is not None else 'unknown'
            self.logger.info(f"消息类型: {msg_type}")
            
            title = appmsg.find('title').text if appmsg.find('title') is not None else ''
            file_ext = appmsg.find('.//fileext').text if appmsg.find('.//fileext') is not None else ''

            attach = appmsg.find('.//appattach')
            if attach is not None:
                file_size = attach.find('totallen').text if attach.find('totallen') is not None else '0'
                cdn_url = attach.find('cdnattachurl').text if attach.find('cdnattachurl') is not None else ''
                aes_key = attach.find('aeskey').text if attach.find('aeskey') is not None else ''

                self.logger.info(f"收到文件消息 - 来自: {context.from_user}")
                self.logger.info(f"文件名: {title}, 类型: {file_ext}, 大小: {file_size}字节")
                self.logger.info(f"文件CDN URL: {cdn_url}")
                self.logger.info(f"文件AES Key: {aes_key}")

                context.processed_data.update({
                    'file_name': title,
                    'file_ext': file_ext,
                    'file_size': int(file_size),
                    'cdn_url': cdn_url,
                    'aes_key': aes_key,
                    'msg_type': msg_type
                })
                return True

        self.logger.error("文件消息缺少必要的信息")
        return False


class MessageProcessor:
    """消息处理器管理类"""

    def __init__(self):
        self.root_handlers: List[MessageHandler] = []
        self.logger = logging.getLogger('WeChatBot')
        self.token = None

    def set_token(self, token: str):
        """设置token"""
        self.token = token

    def add_handler(self, handler: MessageHandler) -> MessageHandler:
        """添加一级处理器"""
        self.root_handlers.append(handler)
        return handler

    async def process_message(self, message: Dict[str, Any]):
        """处理接收到的消息"""
        context = MessageContext(message)

        # 并行处理所有根处理器
        tasks = [handler.process(context) for handler in self.root_handlers]
        results = await asyncio.gather(*tasks)

        # 检查所有根处理器是否都完成了处理
        all_complete = all(handler.processing_complete for handler in self.root_handlers)
        if all_complete:
            self.logger.info("所有处理器已完成消息处理")
        else:
            self.logger.warning("部分处理器未完成处理")