import unittest
import asyncio
from handlers.handlers import MessageContext
from handlers.group_monitor_handler import GroupMonitorHandler

class TestGroupMonitorHandler(unittest.TestCase):
    async def asyncSetUp(self):
        # 测试配置
        self.config = {
            'message_monitor': {
                'target_groups': ['48922992214@chatroom', '43500136128@chatroom'],
                'database': {
                    'type': 'sqlite',
                    'path': ':memory:'  # 使用内存数据库进行测试
                },
                'storage': {
                    'save_media': False,  # 测试时不保存媒体文件
                    'media_path': 'data/test_media'
                }
            }
        }
        self.handler = await GroupMonitorHandler.create(self.config)

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.asyncSetUp())

    def tearDown(self):
        # 关闭数据库连接
        if hasattr(self, 'handler'):
            self.loop.run_until_complete(self.handler.store.close())
        # 清理事件循环
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_init(self):
        """测试初始化"""
        self.assertEqual(len(self.handler.target_groups), 2)
        self.assertFalse(self.handler.save_media)

    def test_can_handle(self):
        """测试消息处理条件判断"""
        # 创建测试消息上下文
        context = MessageContext({
            'TypeName': 'Text',
            'Appid': 'wx_test',
            'Wxid': '48922992214@chatroom',
            'Data': {
                'MsgType': 1,
                'FromUserName': {'string': '48922992214@chatroom'},
                'ToUserName': {'string': 'user123'},
                'Content': {'string': 'Test message'}
            }
        })
        
        # 使用当前事件循环运行异步测试
        result = self.loop.run_until_complete(self.handler.can_handle(context))
        self.assertTrue(result)

        # 测试非目标群消息
        context.from_user = 'other_group@chatroom'
        result = self.loop.run_until_complete(self.handler.can_handle(context))
        self.assertFalse(result)

    def test_handle_text_message(self):
        """测试文本消息处理"""
        context = MessageContext({
            'TypeName': 'Text',
            'Appid': 'wx_test',
            'Wxid': '48922992214@chatroom',
            'Data': {
                'MsgType': 1,
                'FromUserName': {'string': '48922992214@chatroom'},
                'ToUserName': {'string': 'user123'},
                'Content': {'string': 'Test message'}
            }
        })
        
        result = self.loop.run_until_complete(self.handler.handle(context))
        self.assertTrue(result)

    def test_handle_image_message(self):
        """测试图片消息处理"""
        context = MessageContext({
            'TypeName': 'Image',
            'Appid': 'wx_test',
            'Wxid': '48922992214@chatroom',
            'Data': {
                'MsgType': 3,
                'FromUserName': {'string': '48922992214@chatroom'},
                'ToUserName': {'string': 'user123'},
                'Content': {'string': 'image content'}
            }
        })
        
        result = self.loop.run_until_complete(self.handler.handle(context))
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main() 