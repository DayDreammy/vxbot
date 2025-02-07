import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import argparse

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)


from sender import MessageSender  # noqa
from config import Config  # noqa


async def send_message(to_wxid="wxid_w07vyucbgsio29", text_message="hello,来自vxbot", config=None):
    # 初始化 MessageSender
    sender = MessageSender()

    if config is None:
        config = Config().config
    app_id = config['wechat']['app_id']

    try:
        # 发送消息
        if text_message is None:
            text_message = "hello,来自vxbot"

        result = await sender.send_text(app_id, to_wxid, text_message)

        if result:
            print(f"消息发送成功！接收者: {to_wxid}\n消息内容:{text_message}")
        else:
            print("消息发送失败")

    except Exception as e:
        print(f"发送消息时发生错误: {e}")


async def test_send_message(config=None):
    # 初始化 MessageSender
    sender = MessageSender()

    if config is None:
        config = Config().config
    app_id = config['wechat']['app_id']

    to_wxid = "wxid_w07vyucbgsio29"  # 替换为你要发送消息的用户 ID

    # 获取当前时间
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    test_message = f"这是一条hook消息，来自自动化测试脚本，每半小时发送一次。祝你好运！\n————现在是北京时间：{current_time}"

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
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='发送微信消息的脚本')
    parser.add_argument('--to', type=str, default="wxid_w07vyucbgsio29",
                        help='接收消息的微信ID')
    parser.add_argument('--message', type=str, default=None,
                        help='要发送的消息内容')

    args = parser.parse_args()

    # 运行测试
    asyncio.run(send_message(args.to, args.message))
