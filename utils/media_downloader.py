import aiohttp
import asyncio
from pathlib import Path
import logging
from Crypto.Cipher import AES
import base64
import hashlib
import os

class MediaDownloader:
    """媒体文件下载器"""
    
    def __init__(self, save_path: str = 'data/media', api_host: str = None, token: str = None):
        self.save_path = Path(save_path)
        self.logger = logging.getLogger('WeChatBot')
        self.session = None
        self.api_host = api_host or "http://localhost:2531"
        # 从api_host中提取服务器IP，并构造下载主机地址
        server_ip = self.api_host.split('//')[1].split(':')[0]
        self.download_host = f"http://{server_ip}:2532"
        self.token = token
        
    async def ensure_session(self):
        """确保 aiohttp session 存在"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()
            self.session = None
            
    def _decrypt_file(self, encrypted_data: bytes, aes_key: str) -> bytes:
        """使用AES密钥解密数据"""
        try:
            # 解码base64格式的密钥
            key = base64.b64decode(aes_key)
            # 使用ECB模式（微信使用的模式）
            cipher = AES.new(key, AES.MODE_ECB)
            # 解密数据
            decrypted_data = cipher.decrypt(encrypted_data)
            # 去除PKCS7填充
            padding_length = decrypted_data[-1]
            return decrypted_data[:-padding_length]
        except Exception as e:
            self.logger.error(f"解密失败: {e}")
            return encrypted_data
            
    async def download_file(self, cdn_url: str, aes_key: str, file_name: str, app_id: str = None, xml_content: str = None) -> str:
        """
        下载并解密文件
        :param cdn_url: CDN URL
        :param aes_key: AES密钥
        :param file_name: 文件名
        :param app_id: 应用ID
        :param xml_content: 原始XML内容
        :return: 保存的文件路径
        """
        try:
            await self.ensure_session()
            
            # 检查必需参数
            if not app_id:
                self.logger.error("缺少必需的appId参数")
                return None
            
            # 创建保存目录
            save_dir = self.save_path / 'downloads'
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成唯一的文件名
            file_path = save_dir / file_name
            
            # 构造下载请求
            # 使用传入的cdn_url作为下载地址
            download_url = cdn_url
            headers = {}
            
            # 添加token头部（如果存在）
            if self.token:
                headers['X-GEWE-TOKEN'] = self.token
            
            self.logger.info(f"开始下载文件: {file_name}")
            self.logger.debug(f"下载URL: {download_url}")
            self.logger.debug(f"请求头: {headers}")
            
            # 直接从CDN URL下载文件
            async with self.session.get(download_url, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"下载失败，状态码: {response.status}")
                    self.logger.error(f"响应内容: {await response.text()}")
                    return None
                
                encrypted_data = await response.read()
                
            # 如果有AES密钥，解密文件
            if aes_key:
                self.logger.info("正在解密文件...")
                decrypted_data = self._decrypt_file(encrypted_data, aes_key)
            else:
                decrypted_data = encrypted_data
                
            # 保存文件
            file_path.write_bytes(decrypted_data)
            self.logger.info(f"文件已保存到: {file_path}")
            
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"下载文件失败: {e}")
            return None
            
    async def download_image(self, cdn_url: str, aes_key: str, message_id: str, app_id: str = None, xml_content: str = None) -> str:
        """
        下载并解密图片
        :param cdn_url: CDN URL
        :param aes_key: AES密钥
        :param message_id: 消息ID
        :param app_id: 应用ID
        :param xml_content: 原始XML内容
        :return: 保存的文件路径
        """
        try:
            await self.ensure_session()
            
            # 检查必需参数
            if not app_id:
                self.logger.error("缺少必需的appId参数")
                return None
                
            if not xml_content:
                self.logger.error("缺少必需的xml参数")
                return None
            
            # 创建保存目录
            save_dir = self.save_path / 'images'
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件路径
            file_path = save_dir / f"{message_id}.jpg"
            
            # 构造下载请求
            download_url = f"{self.api_host}/message/downloadImage"
            headers = {
                'Content-Type': 'application/json'
            }
            
            # 添加token头部（如果存在）
            if self.token:
                headers['X-GEWE-TOKEN'] = self.token
            
            # 构造请求数据
            data = {
                'appId': app_id,
                'type': 2,  # 下载常规图片
                'xml': xml_content
            }
            
            self.logger.info(f"开始下载图片: {message_id}")
            self.logger.debug(f"下载请求数据: {data}")
            
            # 调用API获取下载地址
            async with self.session.post(download_url, json=data, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"API调用失败，状态码: {response.status}")
                    return None
                
                result = await response.json()
                self.logger.debug(f"API响应: {result}")
                
                if result.get('ret') != 200:
                    self.logger.error(f"API调用失败，错误信息: {result.get('msg')}")
                    return None
                
                # 获取实际的文件下载地址
                file_url = f"{self.download_host}/download/{result['data']['fileUrl']}"
                self.logger.debug(f"文件下载地址: {file_url}")
                
                # 下载实际文件
                async with self.session.get(file_url) as file_response:
                    if file_response.status != 200:
                        self.logger.error(f"下载文件失败，状态码: {file_response.status}")
                        self.logger.error(f"响应内容: {await file_response.text()}")
                        return None
                    
                    encrypted_data = await file_response.read()
            
            # 如果有AES密钥，解密文件
            if aes_key:
                self.logger.info("正在解密图片...")
                decrypted_data = self._decrypt_file(encrypted_data, aes_key)
            else:
                decrypted_data = encrypted_data
            
            # 保存文件
            file_path.write_bytes(decrypted_data)
            self.logger.info(f"图片已保存到: {file_path}")
            
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"下载图片失败: {e}")
            return None
        
    async def save_thumb(self, thumb_data: str, message_id: str) -> str:
        """
        保存缩略图
        :param thumb_data: Base64编码的缩略图数据
        :param message_id: 消息ID
        :return: 保存的文件路径
        """
        try:
            # 创建保存目录
            save_dir = self.save_path / 'thumbs'
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件路径
            file_path = save_dir / f"{message_id}_thumb.jpg"
            
            # 解码并保存缩略图
            image_data = base64.b64decode(thumb_data)
            file_path.write_bytes(image_data)
            
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"保存缩略图失败: {e}")
            return None 