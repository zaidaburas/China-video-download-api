"""
API 配置文件
支持环境变量配置代理和其他选项
"""

import os
from typing import Optional, Dict, Any

class Config:
    """API 配置类"""
    
    def __init__(self):
        # 代理配置（可选）
        self.proxy_url: Optional[str] = os.getenv('VIDEO_PROXY_URL')
        
        # 请求间隔配置（秒）
        self.request_sleep_interval: int = int(os.getenv('REQUEST_SLEEP_INTERVAL', '1'))
        self.max_request_sleep_interval: int = int(os.getenv('MAX_REQUEST_SLEEP_INTERVAL', '5'))
        
        # 重试配置
        self.max_retries: int = int(os.getenv('MAX_RETRIES', '3'))
        
        # 超时配置（秒）
        self.socket_timeout: int = int(os.getenv('SOCKET_TIMEOUT', '60'))
        
    def get_proxy_config(self) -> Dict[str, Any]:
        """获取代理配置"""
        config = {}
        if self.proxy_url:
            config['proxy'] = self.proxy_url
            print(f"✅ 使用代理: {self.proxy_url}")
        return config
    
    def get_enhanced_opts(self) -> Dict[str, Any]:
        """获取增强的配置选项"""
        opts = {
            'socket_timeout': self.socket_timeout,
            'retries': self.max_retries,
            'fragment_retries': self.max_retries,
            'extractor_retries': self.max_retries,
            'file_access_retries': self.max_retries,
            'sleep_interval': self.request_sleep_interval,
            'max_sleep_interval': self.max_request_sleep_interval,
        }
        
        # 添加代理配置
        proxy_config = self.get_proxy_config()
        opts.update(proxy_config)
        
        return opts

# 全局配置实例
config = Config()
