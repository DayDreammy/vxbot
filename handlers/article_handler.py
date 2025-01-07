from .handlers import MessageHandler, MessageContext
import logging
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import aiosqlite
from datetime import datetime
import asyncio
from pathlib import Path
import os
from playwright.async_api import async_playwright
import hashlib


class ArticleInfo:
    """文章信息类"""
    def __init__(self, title: str, url: str, summary: str = "", cover_url: str = ""):
        self.title = title
        self.url = url
        self.summary = summary
        self.cover_url = cover_url
        self.content = ""
        self.pdf_path = ""
        self.images = []

    def to_dict(self) -> Dict[str, str]:
        return {
            'title': self.title,
            'url': self.url,
            'summary': self.summary,
            'cover_url': self.cover_url,
            'content': self.content,
            'pdf_path': self.pdf_path,
            'images': self.images
        }


class WeChatArticleHandler(MessageHandler):
    """微信公众号文章消息处理器"""

    def __init__(self, db_path: str = 'data/message_monitor.db', 
                 storage_path: str = 'data/articles'):
        super().__init__()
        self.db_path = db_path
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        (self.storage_path / 'pdfs').mkdir(exist_ok=True)
        (self.storage_path / 'images').mkdir(exist_ok=True)
        
    async def init_db(self):
        """初始化数据库"""
        async with aiosqlite.connect(self.db_path) as db:
            # 创建文章表
            await db.execute("""
            CREATE TABLE IF NOT EXISTS wechat_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT,
                from_user TEXT,
                title TEXT,
                url TEXT UNIQUE,
                summary TEXT,
                cover_url TEXT,
                content TEXT,
                pdf_path TEXT,
                images TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data TEXT,
                processed BOOLEAN DEFAULT FALSE,
                process_time TIMESTAMP
            )
            """)
            await db.commit()

    async def fetch_article_content(self, article: ArticleInfo) -> bool:
        """获取文章内容并保存为PDF"""
        try:
            # 生成基于URL的唯一文件名
            url_hash = hashlib.md5(article.url.encode()).hexdigest()
            pdf_filename = f"{url_hash}.pdf"
            pdf_path = self.storage_path / 'pdfs' / pdf_filename

            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                
                # 访问文章页面
                self.logger.info(f"正在获取文章内容: {article.title}")
                await page.goto(article.url, wait_until='networkidle')
                await page.wait_for_selector('#js_content')

                # 获取文章内容
                content = await page.evaluate('''() => {
                    const content = document.querySelector('#js_content');
                    return content ? content.innerText : '';
                }''')
                article.content = content

                # 获取文章中的图片
                images = await page.evaluate('''() => {
                    const images = Array.from(document.querySelectorAll('#js_content img'));
                    return images.map(img => ({
                        src: img.src,
                        data_src: img.getAttribute('data-src')
                    }));
                }''')

                # 下载图片
                image_paths = []
                for i, img in enumerate(images):
                    img_url = img['data_src'] or img['src']
                    if img_url:
                        img_filename = f"{url_hash}_{i}.jpg"
                        img_path = self.storage_path / 'images' / img_filename
                        try:
                            await page.goto(img_url)
                            await page.screenshot(path=str(img_path))
                            image_paths.append(str(img_path))
                        except Exception as e:
                            self.logger.error(f"下载图片失败: {img_url}, 错误: {e}")

                article.images = image_paths

                # 返回文章页面并保存为PDF
                await page.goto(article.url, wait_until='networkidle')
                await page.pdf(path=str(pdf_path))
                article.pdf_path = str(pdf_path)

                await browser.close()
                return True

        except Exception as e:
            self.logger.error(f"获取文章内容失败: {e}")
            return False

    async def handle(self, context: MessageContext) -> bool:
        try:
            self.logger.info(f"开始处理公众号文章消息 - 来自: {context.from_user}")
            
            # 确保数据库已初始化
            await self.init_db()
            
            # 解析文章信息
            articles = self._parse_articles(context.xml_content)
            if not articles:
                self.logger.error("未找到文章信息")
                return False
                
            # 记录每篇文章的信息并保存到数据库
            async with aiosqlite.connect(self.db_path) as db:
                for i, article in enumerate(articles, 1):
                    self.logger.info(f"文章 {i}:")
                    self.logger.info(f"标题: {article.title}")
                    self.logger.info(f"链接: {article.url}")
                    if article.summary:
                        self.logger.info(f"摘要: {article.summary}")
                    if article.cover_url:
                        self.logger.info(f"封面图片: {article.cover_url}")
                        
                    # 获取文章内容（异步执行，不阻塞消息处理）
                    asyncio.create_task(self._process_article_content(article, context))
                        
                    # 保存到数据库
                    try:
                        await db.execute("""
                        INSERT INTO wechat_articles 
                        (message_id, from_user, title, url, summary, cover_url, raw_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(context.data.get('MsgId', '')),
                            context.from_user,
                            article.title,
                            article.url,
                            article.summary,
                            article.cover_url,
                            json.dumps(context.data, ensure_ascii=False)
                        ))
                    except aiosqlite.IntegrityError:
                        self.logger.info(f"文章已存在: {article.title}")
                        continue
                        
                await db.commit()
                    
            # 将文章信息存储到处理结果中
            context.processed_data.update({
                'msg_type': 'article',
                'articles': [article.to_dict() for article in articles]
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"处理公众号文章消息时发生错误: {e}")
            return False

    async def _process_article_content(self, article: ArticleInfo, context: MessageContext):
        """异步处理文章内容"""
        try:
            # 检查文章是否已经处理过
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT processed, pdf_path FROM wechat_articles WHERE url = ?", 
                    (article.url,)
                )
                row = await cursor.fetchone()
                if row and row[0]:  # 如果文章已处理且处理成功
                    self.logger.info(f"文章已处理过，跳过: {article.title}")
                    return
                elif row and row[1] and os.path.exists(row[1]):  # 如果PDF路径存在且文件存在
                    self.logger.info(f"文章PDF已存在，跳过: {article.title}")
                    return

            # 获取文章内容
            if await self.fetch_article_content(article):
                # 更新数据库
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("""
                    UPDATE wechat_articles 
                    SET content = ?, pdf_path = ?, images = ?, processed = TRUE, process_time = CURRENT_TIMESTAMP
                    WHERE url = ?
                    """, (
                        article.content,
                        article.pdf_path,
                        json.dumps(article.images),
                        article.url
                    ))
                    await db.commit()
                self.logger.info(f"文章内容处理完成: {article.title}")
            else:
                self.logger.error(f"文章内容处理失败: {article.title}")
        except Exception as e:
            self.logger.error(f"处理文章内容时发生错误: {article.title}, {e}")
            
    def _parse_articles(self, xml_content: ET.Element) -> List[ArticleInfo]:
        """解析文章信息"""
        articles = []
        
        # 查找所有文章项
        items = xml_content.findall('.//mmreader//item')
        if not items:
            # 如果没有找到多文章结构，尝试解析单文章结构
            appmsg = xml_content.find('.//appmsg')
            if appmsg is not None:
                title = self._get_text(appmsg, 'title')
                url = self._get_text(appmsg, 'url')
                if title and url:
                    articles.append(ArticleInfo(
                        title=title,
                        url=url,
                        summary=self._get_text(appmsg, 'des'),
                        cover_url=self._get_text(appmsg, './/cover')
                    ))
        else:
            # 解析多文章结构
            for item in items:
                title = self._get_text(item, 'title')
                url = self._get_text(item, 'url')
                if title and url:
                    articles.append(ArticleInfo(
                        title=title,
                        url=url,
                        summary=self._get_text(item, 'summary'),
                        cover_url=self._get_text(item, 'cover')
                    ))
                    
        return articles
        
    def _get_text(self, element: ET.Element, path: str) -> str:
        """安全地获取XML元素的文本内容"""
        child = element.find(path)
        return child.text if child is not None and child.text else "" 

    async def can_handle(self, context: MessageContext) -> bool:
        """检查是否为公众号文章消息"""
        # 检查是否为 type=5 的 appmsg 类型消息
        if context.msg_type != 49:  # appmsg类型
            return False
            
        if context.xml_content is None:
            return False
            
        appmsg = context.xml_content.find('.//appmsg')
        if appmsg is None:
            return False
            
        msg_type = appmsg.find('type')
        return msg_type is not None and msg_type.text == '5'  # 文章类型 