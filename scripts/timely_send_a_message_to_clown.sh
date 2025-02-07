#!/bin/bash

# 获取当前北京时间，假设系统时区设置为北京（CST）, 否则需要使用UTC加8小时
current_time=$(date +"%Y年%m月%d日 %H:%M:%S")

# 运行 Python 脚本，并将格式化的时间包含在消息中
/home/yy/anaconda3/envs/py310/bin/python /home/yy/project/Gewechat/vxbot/utils/send_a_text_message_to_someone.py --to wxid_w07vyucbgsio29 --message "vxbot为您报时，现在是北京时间$current_time"