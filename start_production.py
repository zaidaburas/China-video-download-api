#!/usr/bin/env python3
"""
生产环境优化的视频下载API启动脚本
支持Windows和Linux服务器部署，专门解决连接重置和稳定性问题
"""

import os
import sys
import subprocess
import socket
import psutil
import signal
import time
import logging
import platform
from pathlib import Path
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProductionServerConfig:
    """生产环境服务器配置"""
    
    def __init__(self):
        # 基础配置
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", 8001))
        
        # 性能和稳定性配置
        self.workers = int(os.getenv("WORKERS", 1))  # 单进程避免复杂性
        self.max_requests = int(os.getenv("MAX_REQUESTS", 5000))  # 定期重启worker
        self.max_requests_jitter = int(os.getenv("MAX_REQUESTS_JITTER", 100))
        self.timeout_keep_alive = int(os.getenv("TIMEOUT_KEEP_ALIVE", 5))
        self.timeout_graceful_shutdown = int(os.getenv("TIMEOUT_GRACEFUL_SHUTDOWN", 30))
        
        # 连接配置 - 针对Windows ConnectionResetError优化
        self.limit_max_requests = int(os.getenv("LIMIT_MAX_REQUESTS", 100))
        self.limit_concurrency = int(os.getenv("LIMIT_CONCURRENCY", 50))
        self.backlog = int(os.getenv("BACKLOG", 2048))
        
        # 日志配置
        self.log_level = os.getenv("LOG_LEVEL", "info")
        self.access_log = os.getenv("ACCESS_LOG", "true").lower() == "true"
        
        # 重启配置
        self.auto_restart = os.getenv("AUTO_RESTART", "true").lower() == "true"
        self.restart_delay = int(os.getenv("RESTART_DELAY", 5))
        self.max_restart_attempts = int(os.getenv("MAX_RESTART_ATTEMPTS", 10))

def check_dependencies():
    """检查核心依赖是否安装"""
    required_packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn", 
        "yt-dlp": "yt_dlp",
        "pydantic": "pydantic",
        "requests": "requests",
        "pyyaml": "yaml",
        "psutil": "psutil"
    }
    
    missing_packages = []
    for display_name, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(display_name)
    
    if missing_packages:
        logger.error(f"缺少以下依赖包: {', '.join(missing_packages)}")
        logger.info("请运行: pip install -r requirements.txt")
        return False
    
    logger.info("✅ 所有依赖已安装")
    return True

def check_port_available(port: int) -> bool:
    """检查端口是否可用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except socket.error:
            return False

def find_and_kill_port_process(port: int) -> bool:
    """查找并终止占用端口的进程"""
    try:
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                try:
                    process = psutil.Process(conn.pid)
                    logger.info(f"发现占用端口 {port} 的进程: {process.name()} (PID: {conn.pid})")
                    
                    # 如果是Python进程，很可能是之前的API服务
                    if 'python' in process.name().lower():
                        logger.info(f"终止之前的API服务进程 {conn.pid}")
                        process.terminate()
                        process.wait(timeout=10)
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
        return False
    except Exception as e:
        logger.warning(f"处理端口冲突时出错: {e}")
        return False

def create_temp_dir():
    """创建临时目录"""
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    logger.info("✅ 临时目录已创建")

def build_uvicorn_command(config: ProductionServerConfig) -> list:
    """构建优化的uvicorn启动命令，支持Windows和Linux"""
    cmd = [
        sys.executable, "-m", "uvicorn", "api.main:app",
        "--host", config.host,
        "--port", str(config.port),
        "--workers", str(config.workers),
        "--log-level", config.log_level,
        "--timeout-keep-alive", str(config.timeout_keep_alive),
        "--timeout-graceful-shutdown", str(config.timeout_graceful_shutdown),
        "--limit-max-requests", str(config.limit_max_requests),
        "--limit-concurrency", str(config.limit_concurrency),
        "--backlog", str(config.backlog),
    ]
    
    # 平台特定优化
    system = platform.system().lower()
    if system == 'windows':
        # Windows特定优化 - 解决连接重置问题
        cmd.extend([
            "--loop", "asyncio",
            "--http", "httptools"
        ])
        logger.info("✅ 已应用Windows连接优化")
    elif system == 'linux':
        # Linux特定优化
        cmd.extend([
            "--loop", "uvloop",  # Linux上使用更快的uvloop
            "--http", "httptools"
        ])
        logger.info("✅ 已应用Linux性能优化")
    
    # 访问日志配置
    if not config.access_log:
        cmd.append("--no-access-log")
    
    # 生产环境优化
    if config.max_requests > 0:
        cmd.extend(["--max-requests", str(config.max_requests)])
        if config.max_requests_jitter > 0:
            cmd.extend(["--max-requests-jitter", str(config.max_requests_jitter)])
    
    return cmd

class ServerManager:
    """服务器进程管理器"""
    
    def __init__(self, config: ProductionServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.restart_count = 0
        self.should_restart = True
        
        # 设置信号处理
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._signal_handler)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，准备关闭服务...")
        self.should_restart = False
        self.stop_server()
        sys.exit(0)
    
    def start_server(self) -> bool:
        """启动服务器"""
        try:
            cmd = build_uvicorn_command(self.config)
            logger.info(f"启动命令: {' '.join(cmd)}")
            
            # 启动进程
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            logger.info(f"服务器已启动，PID: {self.process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"启动服务器失败: {e}")
            return False
    
    def stop_server(self):
        """停止服务器"""
        if self.process and self.process.poll() is None:
            logger.info("正在停止服务器...")
            try:
                # 优雅关闭
                self.process.terminate()
                self.process.wait(timeout=self.config.timeout_graceful_shutdown)
            except subprocess.TimeoutExpired:
                logger.warning("优雅关闭超时，强制终止进程")
                self.process.kill()
                self.process.wait()
            
            logger.info("服务器已停止")
    
    def monitor_server(self):
        """监控服务器状态"""
        while self.should_restart:
            if not self.process or self.process.poll() is not None:
                # 进程已退出
                if self.process:
                    exit_code = self.process.returncode
                    logger.warning(f"服务器进程退出，退出码: {exit_code}")
                
                if self.restart_count >= self.config.max_restart_attempts:
                    logger.error(f"达到最大重启次数 ({self.config.max_restart_attempts})，停止重启")
                    break
                
                if self.config.auto_restart and self.should_restart:
                    logger.info(f"等待 {self.config.restart_delay} 秒后重启...")
                    time.sleep(self.config.restart_delay)
                    
                    self.restart_count += 1
                    logger.info(f"尝试重启服务器 (第 {self.restart_count} 次)")
                    
                    if not self.start_server():
                        logger.error("重启失败")
                        break
                else:
                    break
            
            # 检查间隔
            time.sleep(5)
    
    def run(self):
        """运行服务器管理器"""
        logger.info("🚀 启动生产环境视频下载API服务器")
        logger.info("=" * 60)
        
        # 启动服务器
        if not self.start_server():
            return False
        
        logger.info(f"🌐 服务地址: http://{self.config.host}:{self.config.port}")
        logger.info(f"📚 API文档: http://{self.config.host}:{self.config.port}/docs")
        logger.info(f"❤️ 健康检查: http://{self.config.host}:{self.config.port}/api/health")
        logger.info("=" * 60)
        logger.info("按 Ctrl+C 停止服务")
        
        try:
            # 监控服务器
            self.monitor_server()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭服务...")
        finally:
            self.stop_server()
        
        return True

def main():
    """主函数"""
    system = platform.system()
    print("🚀 生产环境视频下载API启动器")
    print(f"🖥️  运行平台: {system}")
    print("🔧 专门优化服务器稳定性和连接问题")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 创建必要目录
    create_temp_dir()
    
    # 加载配置
    config = ProductionServerConfig()
    
    # 检查端口
    if not check_port_available(config.port):
        logger.warning(f"端口 {config.port} 被占用，尝试释放...")
        if not find_and_kill_port_process(config.port):
            logger.error(f"无法释放端口 {config.port}")
            sys.exit(1)
        
        # 等待端口释放
        time.sleep(2)
        if not check_port_available(config.port):
            logger.error(f"端口 {config.port} 仍被占用")
            sys.exit(1)
    
    # 显示配置信息
    logger.info("📋 服务器配置:")
    logger.info(f"   主机: {config.host}")
    logger.info(f"   端口: {config.port}")
    logger.info(f"   工作进程: {config.workers}")
    logger.info(f"   最大请求数: {config.limit_max_requests}")
    logger.info(f"   并发限制: {config.limit_concurrency}")
    logger.info(f"   自动重启: {config.auto_restart}")
    logger.info(f"   日志级别: {config.log_level}")
    
    # 启动服务器管理器
    manager = ServerManager(config)
    success = manager.run()
    
    if not success:
        logger.error("服务器启动失败")
        sys.exit(1)
    
    logger.info("👋 服务已停止")

if __name__ == "__main__":
    main()
