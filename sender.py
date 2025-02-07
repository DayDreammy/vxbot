import logging
from typing import Dict, Optional
from config import Config
import aiohttp


class MessageSender:
    """消息发送类，负责发送不同类型的消息"""

    def __init__(self, config: Optional[Dict] = None):
        if config is None:
            config = Config().config
        self.base_url = config['wechat']['base_url']
        self.token = config['wechat']['token']
        self.logger = logging.getLogger('WeChatBot')

    async def send_text(self, app_id: str, to_wxid: str, content: str) -> bool:
        """
        发送文本消息
        参数：
            app_id: str 应用ID
            to_wxid: str 接收者ID
            content: str 消息内容
            token: str 认证令牌
        返回：
            bool 是否发送成功
        """
        url = f"{self.base_url}/message/postText"
        headers = {"X-GEWE-TOKEN": self.token}
        data = {
            "appId": app_id,
            "toWxid": to_wxid,
            "content": content
        }

        try:
            # 使用aiohttp替代requests进行异步请求
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("ret") == 200:
                            self.logger.info(f"文本消息发送成功 - 接收者: {to_wxid}")
                            return True
                        self.logger.error(
                            f"发送文本消息失败: {result.get('msg', '未知错误')}")
                    else:
                        self.logger.error(
                            f"发送文本消息请求失败: HTTP {response.status}")
        except Exception as e:
            self.logger.error(f"发送文本消息时发生错误: {e}")
        return False

    async def send_processing_message(self, app_id: str, to_wxid: str) -> bool:
        """
        发送正在处理的提示消息
        参数：
            app_id: str 应用ID
            to_wxid: str 接收者ID
            token: str 认证令牌
        返回：
            bool 是否发送成功
        """
        return await self.send_text(
            app_id,
            to_wxid,
            "消息处理中，请等待处理结束再次发送消息。"
        )
