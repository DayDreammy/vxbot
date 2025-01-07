from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
from datetime import datetime
import os
from typing import Dict, Any, Type, Optional, List, Tuple
import threading
import asyncio
import concurrent.futures
from handlers.handlers import MessageProcessor, TextMessageHandler, ImageMessageHandler, FileMessageHandler, MessageHandler
from login import WeChatLogin

from config import Config

class HandlerRegistry:
    """处理器注册表，用于管理处理器的层级关系"""

    def __init__(self):
        self.handlers: List[Tuple[Type[MessageHandler], Optional[Type[MessageHandler]]]] = []
        self.handler_instances: Dict[Type[MessageHandler], MessageHandler] = {}

    def register(self, handler_class: Type[MessageHandler], parent_class: Optional[Type[MessageHandler]] = None):
        """
        注册处理器
        handler_class: 处理器类
        parent_class: 父处理器类（可选）
        """
        self.handlers.append((handler_class, parent_class))

    def build_processor(self) -> MessageProcessor:
        """构建处理器层级结构"""
        processor = MessageProcessor()
        self.handler_instances.clear()

        # 首先创建并添加所有主处理器（没有父处理器的）
        for handler_class, parent_class in self.handlers:
            if parent_class is None:
                instance = handler_class()
                self.handler_instances[handler_class] = processor.add_handler(instance)

        # 循环添加子处理器，直到所有处理器都被添加
        while True:
            added_count = 0
            for handler_class, parent_class in self.handlers:
                # 如果这个处理器还没有被创建实例，且其父处理器已经有实例
                if (handler_class not in self.handler_instances and
                        parent_class in self.handler_instances):
                    instance = handler_class()
                    self.handler_instances[handler_class] = instance
                    parent_instance = self.handler_instances[parent_class]
                    parent_instance.add_handler(instance)
                    added_count += 1

            # 如果这一轮没有添加任何处理器，说明所有处理器都已添加完成
            if added_count == 0:
                break

        return processor


class AsyncMessageProcessor:
    """异步消息处理器"""

    def __init__(self, max_concurrent_tasks=5):
        self.message_queue = asyncio.Queue()
        self.logger = logging.getLogger()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.is_running = False
        self.tasks = set()
        self.registry = HandlerRegistry()
        self.message_processor = None
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.token = None

    def set_token(self, token: str):
        """设置token"""
        self.token = token

    def register_handler(self, handler_class: Type[MessageHandler],
                         parent_handler: Optional[Type[MessageHandler]] = None):
        """注册处理器"""
        self.registry.register(handler_class, parent_handler)

    def initialize_processor(self):
        """初始化处理器"""
        self.message_processor = self.registry.build_processor()

    async def start(self):
        """启动异步处理"""
        if self.message_processor is None:
            self.initialize_processor()
        self.is_running = True
        self.logger.info("启动异步消息处理器")
        await self._process_messages()

    async def stop(self):
        """停止异步处理"""
        self.is_running = False
        if self.tasks:
            self.logger.info("等待所有任务完成...")
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.logger.info("异步消息处理器已停止")

    async def add_message(self, message: Dict[str, Any]):
        """添加消息到队列"""
        await self.message_queue.put(message)

    async def _process_messages(self):
        """处理消息队列"""
        while self.is_running:
            try:
                while not self.message_queue.empty():
                    message = await self.message_queue.get()
                    task = asyncio.create_task(self._process_single_message(message))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
                await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"处理消息队列时发生错误: {e}")

    async def _process_single_message(self, message: Dict[str, Any]):
        """处理单条消息"""
        async with self.semaphore:
            try:
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    await loop.run_in_executor(
                        pool,
                        self.message_processor.process_message,
                        message
                    )
            except Exception as e:
                self.logger.error(f"处理消息时发生错误: {e}")
            finally:
                self.message_queue.task_done()


class AsyncWeChatBotRequestHandler(BaseHTTPRequestHandler):
    message_processor = None
    logger = None
    loop = None

    @classmethod
    def init_handler(cls, loop, processor):
        cls.message_processor = processor
        cls.loop = loop
        if cls.logger is None:
            cls.logger = setup_logger()

    def do_POST(self):
        if self.path != '/callback':
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {"status": "success", "msg": "消息已接收"}
        self.wfile.write(json.dumps(response).encode())

        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            json_data = json.loads(post_data.decode('utf-8'))

            # 直接在事件循环中运行处理过程
            asyncio.run_coroutine_threadsafe(
                self.message_processor.process_message(json_data),
                self.loop
            )
        except Exception as e:
            if self.logger:
                self.logger.error(f"处理消息时发生错误: {e}")


def setup_logger():
    """设置日志配置"""
    import os
    
    if not os.path.exists('logs'):
        os.makedirs('logs')

    today = datetime.now().strftime('%Y-%m-%d')
    log_file = f'logs/wechat_{today}.log'

    # 从环境变量获取日志级别，默认为INFO
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, log_level, logging.INFO)

    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 获取根日志记录器
    logger = logging.getLogger('WeChatBot')

    # 如果logger已经有处理器，说明已经被初始化过，直接返回
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台处理器 - 总是使用INFO级别，避免控制台输出过多信息
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # systemd journal处理器 - 使用与主日志相同的级别
    try:
        from systemd import journal
        journal_handler = journal.JournalHandler(
            SYSLOG_IDENTIFIER='wechat-bot'
        )
        journal_handler.setLevel(level)
        journal_handler.setFormatter(formatter)
        logger.addHandler(journal_handler)
    except ImportError:
        logger.debug("systemd journal模块未安装，跳过journal日志配置")

    # 阻止日志向上传播到根记录器
    logger.propagate = False

    logger.debug(f"日志系统初始化完成，级别: {log_level}")
    return logger


class AsyncWeChatBotServer:
    def __init__(self, port=8069):
        from handlers.group_monitor_handler import GroupMonitorHandler
        self.GroupMonitorHandler = GroupMonitorHandler
        self.port = port
        self.httpd = None
        self.logger = setup_logger()
        self.loop = None
        
        # 加载配置
        self.config = Config().config
        
        # 使用新的MessageProcessor替代AsyncMessageProcessor
        self.message_processor = MessageProcessor()
        # 从 login 获取 token
        self.login = WeChatLogin()
        if not self.login.get_token():
            raise Exception("获取 token 失败")
        self.message_processor.set_token(self.login.token)

    def register_handler(self, handler_class: Type[MessageHandler],
                         parent_handler: Optional[Type[MessageHandler]] = None):
        """注册处理器"""
        # 创建处理器实例
        if handler_class == self.GroupMonitorHandler:
            handler = handler_class(self.config)
        else:
            handler = handler_class()

        if parent_handler is None:
            # 如果没有父处理器，直接添加到根处理器列表
            self.message_processor.add_handler(handler)
        else:
            # 如果有父处理器，遍历所有处理器找到父处理器并添加
            def add_to_parent(current_handler):
                if isinstance(current_handler, parent_handler):
                    current_handler.add_handler(handler)
                    return True
                for next_handler in current_handler.next_handlers:
                    if add_to_parent(next_handler):
                        return True
                return False

            # 遍历所有根处理器
            for root_handler in self.message_processor.root_handlers:
                if add_to_parent(root_handler):
                    break

    def start(self):
        """启动服务器"""
        self.logger.info(f'服务器启动在端口 {self.port}...')

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        AsyncWeChatBotRequestHandler.logger = self.logger
        AsyncWeChatBotRequestHandler.init_handler(self.loop, self.message_processor)

        server_address = ('', self.port)
        self.httpd = HTTPServer(server_address, AsyncWeChatBotRequestHandler)

        thread = threading.Thread(target=self._run_event_loop, daemon=True)
        thread.start()

        try:
            self.httpd.serve_forever()
        except Exception as e:
            self.logger.error(f"服务器运行错误: {e}")

    def _run_event_loop(self):
        """在独立线程中运行事件循环"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self):
        """停止服务器"""
        if self.httpd:
            self.logger.info("正在停止服务器...")
            self.httpd.shutdown()

        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)


# # 使用示例
# class ExcelHandler(MessageHandler):
#     def can_handle(self, context: MessageContext) -> bool:
#         return (context.msg_type == 49 and
#                 context.processed_data.get('file_ext') == 'xlsx')
#
#     def handle(self, context: MessageContext) -> bool:
#         self.logger.info(f"处理Excel文件: {context.processed_data['file_name']}")
#         return True
#
#
# class SalesExcelHandler(MessageHandler):
#     def can_handle(self, context: MessageContext) -> bool:
#         return "sales" in context.processed_data.get('file_name', '').lower()
#
#     def handle(self, context: MessageContext) -> bool:
#         self.logger.info(f"处理销售数据Excel文件: {context.processed_data['file_name']}")
#         return True


def run_server(port=8069):
    server = AsyncWeChatBotServer(port)

    # 注册基础处理器
    server.register_handler(TextMessageHandler)
    server.register_handler(ImageMessageHandler)
    server.register_handler(FileMessageHandler)

    # 注册文章处理器
    from handlers.article_handler import WeChatArticleHandler
    server.register_handler(WeChatArticleHandler)

    # 注册单次提交处理器
    from handlers.singleSubmitHandler.single_submit_handler import SingleSubmitHandler
    server.register_handler(SingleSubmitHandler,TextMessageHandler)

    # 注册群组监控处理器
    from handlers.group_monitor_handler import GroupMonitorHandler
    server.register_handler(GroupMonitorHandler, TextMessageHandler)

    # 注释掉这两行来禁用 AI 聊天功能
    # from handlers.singleSubmitHandler.aiChatHandler.ai_chat_handler import AIChatHandler
    # server.register_handler(AIChatHandler, SingleSubmitHandler)

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
        print("\n服务器已停止")


if __name__ == '__main__':
    run_server()