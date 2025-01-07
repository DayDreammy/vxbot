import requests
import os

import yaml
from PIL import Image
import base64
import logging
from datetime import datetime
import sys
import time
from config import Config
from alerts import AlertManager


class WeChatLogin:
    """微信登录和状态监控类"""
    def __init__(self):
        """初始化微信登录模块"""
        self.config = Config()
        self.base_url = self.config.config['wechat']['base_url']
        self.alert_manager = AlertManager(self.config.config)
        self.token = None
        self.headers = {}
        self.current_app_id = None
        self.current_uuid = None
        self.setup_logger()

    def setup_logger(self):
        """设置日志记录器"""
        # 创建logs目录（如果不存在）
        if not os.path.exists('logs'):
            os.makedirs('logs')

        # 获取今天的日期作为文件名
        today = datetime.now().strftime('%Y-%m-%d')
        log_file = f'logs/wechat_{today}.log'

        # 配置日志格式
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        # 配置logger
        self.logger = logging.getLogger('WeChatBot')
        self.logger.setLevel(logging.INFO)

        # 清除可能存在的旧处理器
        self.logger.handlers = []

        # 添加处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def load_credentials(self):
        """
        从配置文件加载appId
        返回：
            str appId 或 None
        """
        try:
            app_id = self.config.config['wechat'].get('app_id')
            if app_id:
                return app_id, None
            return None, None
        except Exception as e:
            self.logger.error(f"读取appId失败: {e}")
            return None, None

    def check_online_status(self):
        """
        检查是否在线
        返回：
            bool 是否在线
        """
        app_id, _ = self.load_credentials()
        if not app_id:
            self.logger.info("未找到已保存的AppID")
            return False

        if not self.get_token():
            return False

        url = f"{self.base_url}/login/checkOnline"
        check_data = {
            "appId": app_id
        }

        try:
            response = requests.post(url, headers=self.headers, json=check_data)
            if response.status_code == 200:
                data = response.json()
                if data.get("ret") == 200:
                    is_online = data.get("data", False)
                    if is_online:
                        self.logger.info("账号在线")
                        return True
                    self.logger.info("账号离线")
                else:
                    self.logger.warning(f"检查在线状态失败: {data.get('msg', '未知错误')}")
            else:
                self.logger.error(f"检查在线状态请求失败: HTTP {response.status_code}")
        except Exception as e:
            self.logger.error(f"检查在线状态出错: {e}")
        return False

    def save_credentials(self, app_id, token):
        """
        保存appId和token到配置文件
        """
        try:
            with open(self.config.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            config['wechat']['app_id'] = app_id
            config['wechat']['token'] = token

            with open(self.config.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True)

            self.logger.info("凭证已保存到配置文件")
        except Exception as e:
            self.logger.error(f"保存凭证失败: {e}")

    def get_token(self):
        """
        优先从配置文件获取token，如果没有则重新获取
        """
        if self.config.config['wechat'].get('token'):
            self.token = self.config.config['wechat']['token']
            self.headers = {"X-GEWE-TOKEN": self.token}
            return True

        url = f"{self.base_url}/tools/getTokenId"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                data = response.json()
                if data["ret"] == 200:
                    self.token = data["data"]
                    self.headers = {"X-GEWE-TOKEN": self.token}
                    # 保存到配置文件
                    self.save_credentials(self.config.config['wechat'].get('app_id', ''),
                                          self.token)
                    self.logger.info(f"Token获取成功: {self.token}")
                    return True
                self.logger.error(f"Token获取失败: {data.get('msg', '未知错误')}")
            else:
                self.logger.error(f"Token请求失败: HTTP {response.status_code}")
        except Exception as e:
            self.logger.error(f"获取Token出错: {e}")
        return False

    def get_qr_code(self):
        """
        获取登录二维码
        返回：
            bool 是否成功获取二维码
        """
        url = f"{self.base_url}/login/getLoginQrCode"
        app_id, _ = self.load_credentials()
        response = requests.post(url, headers=self.headers, json={"appId": app_id or ""})

        if response.status_code == 200:
            data = response.json()
            if data["ret"] == 200:
                try:
                    self.current_app_id = data["data"]["appId"]
                    self.current_uuid = data["data"]["uuid"]
                    self.logger.info(f"获取到 appId: {self.current_app_id}")
                    self.logger.info(f"获取到 uuid: {self.current_uuid}")

                    qr_base64 = data["data"]["qrImgBase64"]
                    if "data:image" in qr_base64:
                        qr_base64 = qr_base64.split(",")[1]

                    qr_base64 = qr_base64.strip()

                    # 保存二维码图片
                    img_data = base64.b64decode(qr_base64)
                    qr_path = "qr_code.png"
                    with open(qr_path, "wb") as f:
                        f.write(img_data)

                    self.logger.info(f"二维码已保存到: {os.path.abspath(qr_path)}")
                    
                    # 尝试使用不同的方法显示二维码
                    try:
                        # 1. 尝试使用终端QR码显示（如果安装了qrcode库）
                        try:
                            import qrcode
                            qr = qrcode.QRCode()
                            qr.add_data(data["data"]["url"])  # 假设API返回了url字段
                            qr.print_ascii()
                            self.logger.info("二维码已在终端显示")
                        except (ImportError, KeyError):
                            pass

                        # 2. 提供在线查看链接（如果API返回了url）
                        if "url" in data["data"]:
                            self.logger.info(f"二维码链接: {data['data']['url']}")
                        
                    except Exception as e:
                        self.logger.warning(f"显示二维码时出现问题: {e}")
                    
                    return True
                except Exception as e:
                    self.logger.error(f"处理二维码图片失败: {e}")
                    return False
        self.logger.error("获取二维码失败")
        return False

    def check_login(self):
        """
        检查登录状态
        返回：
            bool 是否登录成功
        """
        if not self.current_app_id or not self.current_uuid:
            self.logger.error("缺少必要的appId或uuid参数")
            return False

        url = f"{self.base_url}/login/checkLogin"
        check_data = {
            "appId": self.current_app_id,
            "uuid": self.current_uuid
        }
        response = requests.post(url, headers=self.headers, json=check_data)

        if response.status_code == 200:
            data = response.json()
            if data.get("ret") == 200:
                self.logger.info("登录成功")
                self.save_credentials(self.current_app_id, self.token)
                return True
            else:
                self.logger.warning(f"登录检查失败: {data.get('msg', '未知错误')}")
        return False

    def set_callback(self):
        """
        设置回调URL
        返回：
            bool 是否成功设置回调
        """
        url = f"{self.base_url}/tools/setCallback"
        callback_data = {
            "token": self.token,
            "callbackUrl": self.config.config['wechat']['callback_url']
        }
        try:
            response = requests.post(url, headers=self.headers, json=callback_data)
            if response.status_code == 200:
                data = response.json()
                if data.get("ret") == 200:
                    self.logger.info("回调设置成功")
                    return True
                self.logger.warning(f"设置回调失败: {data.get('msg', '未知错误')}")
            else:
                self.logger.error(f"设置回调请求失败: HTTP {response.status_code}")
        except Exception as e:
            self.logger.error(f"设置回调出错: {e}")
        return False
    def monitor_status(self):
        """持续监控登录状态"""
        check_interval = self.config.config['monitoring']['check_interval']
        self.logger.info(f"开始监控登录状态，检查间隔: {check_interval}秒")

        while True:
            if not self.check_online_status():
                self.logger.error("检测到账号离线")
                self.alert_manager.send_alerts("WeChat Bot已离线，请检查状态！")
                break

            self.logger.info(f"状态检查正常，等待{check_interval}秒后重新检查...")
            time.sleep(check_interval)


def main():
    """主函数：程序入口"""
    login = WeChatLogin()
    login.logger.info("=== 程序启动 ===")

    # 检查在线状态
    if login.check_online_status():
        login.logger.info("账号在线，开始监控状态...")
        login.monitor_status()
        return

    login.logger.info("账号离线，开始登录流程...")

    # 获取token
    if not login.token and not login.get_token():
        login.logger.error("=== 程序结束：获取Token失败 ===")
        return

    # 获取并显示二维码
    if not login.get_qr_code():
        login.logger.error("=== 程序结束：获取二维码失败 ===")
        return

    # 等待用户扫描二维码
    while True:
        user_input = input("请扫描二维码后输入y继续: ")
        if user_input.lower() == 'y':
            break

    # 检查登录状态
    if not login.check_login():
        login.logger.error("=== 程序结束：登录失败 ===")
        return

    # 设置回调
    if not login.set_callback():
        login.logger.error("=== 程序结束：设置回调失败 ===")
        return

    login.logger.info("登录成功，开始监控状态...")
    login.monitor_status()


if __name__ == "__main__":
    main()