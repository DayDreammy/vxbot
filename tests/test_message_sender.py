
import asyncio
import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)


from sender import MessageSender  # noqa
from config import Config  # noqa


async def test_send_message(config=None):
    # 初始化 MessageSender
    sender = MessageSender()

    if config is None:
        config = Config().config
    app_id = config['wechat']['app_id']

    # 设置测试参数
    # app_id = "wx_AS5eTRwpCC2spVAt9ovsV"  # 替换为你的实际 app_id
    to_wxid = "wxid_w07vyucbgsio29"  # 替换为你要发送消息的用户 ID
    test_message = "这是一条测试消息，来自自动化测试脚本"

    try:
        # 发送消息
        result = await sender.send_text(app_id, to_wxid, test_message)

        if result:
            print(f"消息发送成功！接收者: {to_wxid}")
        else:
            print("消息发送失败")

    except Exception as e:
        print(f"发送消息时发生错误: {e}")

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_send_message())
