import os
import logging
import sqlite3
import subprocess
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv


class Device:
    def __init__(self, id=None, hostname=None, ip=None, loss_rate=None, version=None):
        self.id = id
        self.hostname = hostname
        self.ip = ip
        self.loss_rate = loss_rate
        self.version = version
    
    @classmethod
    def from_json(cls, json_data):
        """
        从JSON数据初始化Device对象
        """
        # 注意：JSON中的数据类型全是字符串，需要转换
        loss_rate_str = json_data.get('loss_rate', '0.0')
        loss_rate = 0.0 if loss_rate_str == '-' else float(loss_rate_str)
        
        return cls(
            id=int(json_data.get('id', 0)),
            hostname=json_data.get('hostname', ''),
            ip=json_data.get('ipv4', ''),
            loss_rate=loss_rate,
            version=json_data.get('version', '')
        )
    
    @classmethod
    def from_db_row(cls, row):
        """
        从数据库行初始化Device对象
        """
        return cls(
            id=row[0],
            hostname=row[1],
            ip=row[2],
            loss_rate=row[3],
            version=row[4]
        )
    
    def save_to_db(self, conn):
        """
        保存自身到数据库
        """
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO devices (id, hostname, ip, loss_rate, version)
            VALUES (?, ?, ?, ?, ?)
        ''', (self.id, self.hostname, self.ip, self.loss_rate, self.version))
        conn.commit()
    
    def compare(self, other):
        """
        对比自身与另一个Device对象，返回差异描述文本
        """
        if not isinstance(other, Device):
            return "类型不匹配，无法比较"
        
        differences = []
        
        if self.hostname != other.hostname:
            differences.append(f"主机名: {self.hostname} -> {other.hostname}")
            
        if self.ip != other.ip:
            differences.append(f"IP地址: {self.ip} -> {other.ip}")
            
        # 丢包率比较：仅在新旧数值中至少一个大于0.02，且相对变化量大于5%时才认为有差异
        if self.loss_rate != other.loss_rate:
            max_rate = max(self.loss_rate, other.loss_rate)
            min_rate = min(self.loss_rate, other.loss_rate)
            
            # 判断是否至少一个大于0.02
            if max_rate > 0.02:
                # 计算相对变化量
                if max_rate > 0:  # 避免除零错误
                    relative_change = (max_rate - min_rate) / max_rate
                    if relative_change > 0.05:  # 大于5%
                        differences.append(f"丢包率: {self.loss_rate} -> {other.loss_rate}")
                elif min_rate > 0:  # 如果max_rate为0但min_rate大于0
                    differences.append(f"丢包率: {self.loss_rate} -> {other.loss_rate}")
            
        if self.version != other.version:
            differences.append(f"版本: {self.version} -> {other.version}")
            
        if differences:
            return f"设备 {self.hostname}({self.ip}) 发生变化: " + ", ".join(differences)
        else:
            return ""  # 无变化
    
    def summary(self):
        """
        生成自身简述文本
        """
        return f"设备 {self.hostname}({self.ip}) ID:{self.id} 版本:{self.version} 丢包率:{self.loss_rate}"


class Config:
    def __init__(self):
        # 初始化所有配置项为None
        self.easy_tier_peer_command = None
        self.daily_report_time = None
        self.check_interval_seconds = None
        self.web_hook_template = None
        self.logging_level = None
        
        try:
            # 加载.env文件
            load_dotenv()
            
            # EasyTier命令
            self.easy_tier_peer_command = self._get_config('EASY_TIER_PEER_COMMAND')
            
            # 每日报告时间
            self.daily_report_time = self._get_config('DAILY_REPORT_TIME')
            
            # 检查间隔秒数
            check_interval = self._get_config('CHECK_INTERVAL_SECONDS')
            self.check_interval_seconds = int(check_interval) if check_interval is not None else None
            
            # WebHook模板
            self.web_hook_template = self._get_config('WEB_HOOK_TEMPLATE')
            
            # Logging级别
            self.logging_level = self._get_config('LOGGING_LEVEL')
        except Exception:
            # 任何异常都将导致配置初始化失败，保持所有字段为None
            pass
    
    def _get_config(self, key):
        """
        获取配置值，环境变量优先于.env文件
        如果都不存在则返回None
        """
        value = os.getenv(key)
        return value if value is not None else None
    
    def is_valid(self):
        """
        检查配置是否初始化成功
        当所有必需的配置项都不为None时，返回True
        """
        required_configs = [
            self.easy_tier_peer_command,
            self.daily_report_time,
            self.check_interval_seconds,
            self.web_hook_template
        ]
        
        return all(config is not None for config in required_configs)


def init_database():
    """
    初始化内存数据库
    创建设备信息表
    """
    # 创建内存数据库连接
    conn = sqlite3.connect(':memory:')
    
    # 创建表
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE devices (
            id INTEGER PRIMARY KEY,
            hostname TEXT,
            ip TEXT,
            loss_rate REAL,
            version TEXT
        )
    ''')
    
    conn.commit()
    logging.info("内存数据库初始化完成")
    return conn


def get_current_devices(config):
    """
    执行命令获取当前设备列表
    """
    try:
        result = subprocess.run(
            config.easy_tier_peer_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            devices_data = json.loads(result.stdout)
            devices = [Device.from_json(data) for data in devices_data]
            return devices
        else:
            logging.error(f"执行命令失败: {result.stderr}")
            return []
    except subprocess.TimeoutExpired:
        logging.error("执行命令超时")
        return []
    except json.JSONDecodeError:
        logging.error("解析JSON失败")
        return []
    except Exception as e:
        logging.error(f"执行命令时发生错误: {e}")
        return []


def get_stored_devices(conn):
    """
    从数据库获取已存储的设备列表
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, hostname, ip, loss_rate, version FROM devices")
    rows = cursor.fetchall()
    return [Device.from_db_row(row) for row in rows]


def send_webhook_message(config, message):
    """
    发送WebHook消息
    """
    if not message:
        return
    
    try:
        webhook_url = config.web_hook_template.replace("{{ ETT_MSG }}", message)
        response = requests.get(webhook_url, timeout=10)
        if response.status_code == 200:
            logging.info("WebHook消息发送成功")
        else:
            logging.error(f"WebHook消息发送失败，状态码: {response.status_code}")
    except Exception as e:
        logging.error(f"发送WebHook消息时发生错误: {e}")


def should_send_daily_report(config):
    """
    检查是否应该发送每日报告
    """
    try:
        report_time = datetime.strptime(config.daily_report_time, "%H:%M").time()
        current_time = datetime.now().time()
        
        # 计算时间差（秒）
        time_diff = abs(
            (current_time.hour * 3600 + current_time.minute * 60 + current_time.second) -
            (report_time.hour * 3600 + report_time.minute * 60)
        )
        
        # 默认时间差异为30秒
        report_time_diff_seconds = 30
        return time_diff < report_time_diff_seconds
    except Exception as e:
        logging.error(f"检查每日报告时间时发生错误: {e}")
        return False


def clear_database(conn):
    """
    清空数据库中的设备数据
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM devices")
    conn.commit()


def main():
    # 读取配置
    config = Config()
    
    # 初始化logging
    logging_level = getattr(logging, config.logging_level, logging.INFO) if config.logging_level else logging.INFO
    logging.basicConfig(
        level=logging_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 检查配置是否正确
    if config.is_valid():
        logging.info("配置检查通过")
        logging.info(f"EasyTier命令: {config.easy_tier_peer_command}")
        logging.info(f"每日报告时间: {config.daily_report_time}")
        logging.info(f"检查间隔秒数: {config.check_interval_seconds}")
        logging.info(f"WebHook模板: {config.web_hook_template}")
        logging.info(f"日志级别: {config.logging_level}")
    else:
        logging.error("配置检查失败，缺少必要的配置项")
        return False
    
    # 初始化内存数据库
    db_conn = init_database()
    
    # 主循环
    while True:
        try:
            # 获取当前设备列表
            current_devices = get_current_devices(config)
            logging.info(f"获取到 {len(current_devices)} 个设备")
            
            # 获取数据库中存储的设备列表
            stored_devices = get_stored_devices(db_conn)
            stored_devices_dict = {device.id: device for device in stored_devices}
            
            # 比较设备变化
            change_messages = []
            
            # 检查新增和变更的设备
            current_devices_dict = {device.id: device for device in current_devices}
            for device in current_devices:
                if device.id not in stored_devices_dict:
                    # 新增设备
                    change_messages.append(f"新上线机器: {device.summary()}")
                else:
                    # 检查设备是否有变化
                    stored_device = stored_devices_dict[device.id]
                    diff = stored_device.compare(device)
                    if diff:
                        change_messages.append(diff)
            
            # 检查下线的设备
            for device in stored_devices:
                if device.id not in current_devices_dict:
                    # 设备下线
                    change_messages.append(f"刚刚下线: {device.summary()}")
            
            # 合并变化消息
            change_message = "\n".join(change_messages)
            
            # 发送变化消息
            if change_message:
                logging.info(f"检测到变化:\n{change_message}")
                send_webhook_message(config, change_message)
            else:
                logging.info("未检测到设备变化")
            
            # 检查是否需要发送每日报告
            if should_send_daily_report(config):
                all_devices_summary = "\n".join([device.summary() for device in current_devices])
                daily_report_message = f"当前所有设备状态:\n{all_devices_summary}"
                logging.info(f"发送每日报告:\n{daily_report_message}")
                send_webhook_message(config, daily_report_message)
            
            # 清空数据库并保存当前设备数据
            clear_database(db_conn)
            for device in current_devices:
                device.save_to_db(db_conn)
            
            # 等待下次检查
            logging.info(f"等待 {config.check_interval_seconds} 秒后进行下次检查...")
            time.sleep(config.check_interval_seconds)
            
        except KeyboardInterrupt:
            logging.info("收到中断信号，程序退出")
            break
        except Exception as e:
            logging.error(f"主循环中发生错误: {e}")
            time.sleep(config.check_interval_seconds)


if __name__ == "__main__":
    main()