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
import sys
import sqlite3

sys.path.append('/home/yy/project/liujing-project-zhengquan')
from src.celery_task.tasks import llm_summary_task

IF_ACCOUNT_WHITELIST = False

# 微信相关配置
WECHAT_FILTERS = {
    # 公众号白名单
    'account_whitelist': {
        '信息平权',
        '计墨社',
        '刘翔科技研究',
        '集微网',
        '未来半导体',
        '半导体行业联盟',
        'AR圈',
        '蓝猫研究所',
        'gh_7d107b7b55f4'  # 摩尔芯闻
    },
    
    # 群聊白名单
    'group_whitelist': {
        '48922992214@chatroom',
        '43500136128@chatroom'
    }
}

# 行业映射配置
INDUSTRY_MAPPING = {
    # 公众号到行业的映射
    'wechat_account_industry': {
        '信息平权': ['电子', '通信'],
        '计墨社': ['电子', '通信'],
        '刘翔科技研究': ['电子', '通信'],
        '集微网': ['电子', '通信'],
        '未来半导体': ['电子', '通信'],
        '半导体行业联盟': ['电子', '通信'],
        'AR圈': ['电子', '通信'],
        '蓝猫研究所': ['电子', '通信'],
        'gh_7d107b7b55f4': ['电子', '通信']  # 摩尔芯闻
    }
}

VXBOT_PATH = '/home/yy/project/Gewechat/vxbot/'



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
        self.storage_path = Path(VXBOT_PATH + storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        (self.storage_path / 'pdfs').mkdir(exist_ok=True)
        (self.storage_path / 'images').mkdir(exist_ok=True)
        
        # 添加统一数据库路径
        self.unified_db_path = Path('/home/yy/project/liujing-project-zhengquan/data/unified_information.db')

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
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 1024}
                )
                page = await context.new_page()
                
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

                # 处理延迟加载的图片
                await page.evaluate('''() => {
                    const images = Array.from(document.querySelectorAll('#js_content img'));
                    images.forEach(img => {
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                            img.style.visibility = 'visible';
                            img.style.opacity = '1';
                            img.removeAttribute('data-src');
                        }
                    });
                }''')

                # 等待所有图片加载完成
                await page.evaluate('''() => {
                    return Promise.all(
                        Array.from(document.querySelectorAll('#js_content img'))
                            .filter(img => !img.complete)
                            .map(img => new Promise(resolve => {
                                img.onload = img.onerror = resolve;
                            }))
                    );
                }''')

                # 获取图片URL列表
                images = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('#js_content img'))
                        .map(img => img.src);
                }''')

                # 下载图片
                image_paths = []
                for i, img_url in enumerate(images):
                    if img_url:
                        img_filename = f"{url_hash}_{i}.jpg"
                        img_path = self.storage_path / 'images' / img_filename
                        try:
                            # 直接下载图片
                            response = await context.request.get(img_url)
                            if response.ok:
                                content = await response.body()
                                img_path.write_bytes(content)
                                image_paths.append(str(img_path))
                            else:
                                self.logger.error(f"下载图片失败: {img_url}, 状态码: {response.status}")
                        except Exception as e:
                            self.logger.error(f"下载图片失败: {img_url}, 错误: {e}")

                article.images = image_paths

                # 注入CSS以优化PDF布局
                await page.add_style_tag(content='''
                    #js_content {
                        padding: 20px !important;
                    }
                    #js_content img {
                        max-width: 100% !important;
                        height: auto !important;
                        margin: 10px 0 !important;
                        page-break-inside: avoid !important;
                        display: block !important;
                    }
                    #js_content * {
                        max-width: 100% !important;
                        word-break: break-word !important;
                    }
                ''')

                # 设置PDF选项并生成PDF
                await page.pdf(**{
                    'path': str(pdf_path),
                    'format': 'A4',
                    'print_background': True,
                    'margin': {
                        'top': '20px',
                        'right': '20px',
                        'bottom': '20px',
                        'left': '20px'
                    }
                })
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

    async def store_to_unified_db(self, article: ArticleInfo, from_user: str) -> Optional[int]:
        """存储文章到统一数据库并返回记录ID"""
        # 检查公众号是否在白名单中
        if IF_ACCOUNT_WHITELIST:
            if from_user not in WECHAT_FILTERS['account_whitelist']:
                self.logger.info(f"公众号 {from_user} 不在白名单中，跳过存储到统一数据库")
                return None
        else:
            self.logger.info(f"公众号 {from_user} , 白名单未开启，存储到统一数据库")    
            
        max_retries = 3
        retry_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            try:
                # 合并摘要和内容，与迁移逻辑保持一致
                content = f"{article.summary}\n{article.content}" if article.content else article.summary
                # 从行业映射获取行业信息
                industries = INDUSTRY_MAPPING['wechat_account_industry'].get(from_user, [])
                industry = ', '.join(industries)
                
                unified_data = (
                    article.title,                # title
                    content,                      # content
                    None,                         # summary
                    article.url,                  # url
                    None,                         # company_name
                    None,                         # stock_code
                    industry,                     # industry
                    '公众号',                      # info_type
                    from_user,                    # source_detail
                    article.pdf_path,             # local_file_path
                    datetime.now(),               # publish_time
                    json.dumps(article.to_dict()) # raw_data
                )
                
                async with aiosqlite.connect(str(self.unified_db_path), timeout=30.0) as db:
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("PRAGMA busy_timeout=5000")
                    
                    cursor = await db.execute("""
                        INSERT INTO unified_information (
                            title, content, summary, url, company_name, 
                            stock_code, industry, info_type, source_detail,
                            local_file_path, publish_time, raw_data
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        RETURNING id
                    """, unified_data)
                    
                    row = await cursor.fetchone()
                    await db.commit()
                    
                    if row:
                        self.logger.info(f"文章已存储到统一数据库，记录ID: {row[0]}")
                        return row[0]
                        
            except sqlite3.IntegrityError:
                self.logger.debug(f"文章已存在于统一数据库中，跳过: {article.title}")
                return None
                
            except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                if "database is locked" in str(e) or "cannot commit" in str(e):
                    if attempt < max_retries - 1:
                        self.logger.warning(f"数据库访问冲突，正在重试 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                self.logger.error(f"存储到统一数据库时发生错误: {e}")
                
            except Exception as e:
                self.logger.error(f"存储到统一数据库时发生错误: {e}")
                
            return None

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
                if row and row[0]:
                    self.logger.info(f"文章已处理过，跳过: {article.title}")
                    return
                elif row and row[1] and os.path.exists(row[1]):
                    self.logger.info(f"文章PDF已存在，跳过: {article.title}")
                    return

            # 获取文章内容
            if await self.fetch_article_content(article):
                # 更新本地数据库
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
                
                # 存储到统一数据库并触发LLM任务
                unified_id = await self.store_to_unified_db(article, context.from_user)
                if unified_id:
                    llm_summary_task.delay([unified_id])
                    self.logger.info(f"已触发LLM摘要任务，记录ID: {unified_id}")
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