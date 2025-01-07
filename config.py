import yaml


class Config:
    """配置管理类，负责加载和管理程序配置"""

    def __init__(self, config_file='config.yml'):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        """
        加载配置文件，如果文件不存在则创建默认配置
        返回：dict 配置数据
        """
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # 默认配置
            default_config = {
                'monitoring': {
                    'check_interval': 30,  # 状态检查间隔（秒）
                },
                'alerts': {
                    'email': {
                        'enabled': False,
                        'smtp_server': 'smtp.gmail.com',
                        'smtp_port': 587,
                        'sender_email': '',
                        'sender_password': '',
                        'recipient_email': ''
                    },
                    'telegram': {
                        'enabled': False,
                        'bot_token': '',
                        'chat_id': ''
                    }
                },
                'wechat': {
                    'base_url': 'http://localhost:2531/v2/api',
                    'callback_url': 'http://localhost:8069/callback',
                    'app_id': '',
                    'token': ''
                },
                # 添加群消息监控配置
                'message_monitor': {
                    'target_groups': [],  # 需要监控的群组ID列表
                    'database': {
                        'type': 'sqlite',
                        'path': 'data/message_monitor.db'
                    },
                    'storage': {
                        'save_media': True,
                        'media_path': 'data/media'
                    }
                }
            }
            # 保存默认配置到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True)
            return default_config

    def update_config(self, new_config):
        """更新配置并保存到文件"""
        self.config.update(new_config)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True)

    def get(self, key, default=None):
        """获取配置项，支持使用点号访问嵌套配置"""
        try:
            value = self.config
            for k in key.split('.'):
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default