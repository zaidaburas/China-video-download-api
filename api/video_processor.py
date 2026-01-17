import os
import yt_dlp
import logging
import requests
import re
import os
from pathlib import Path
from typing import Optional, Dict, Tuple

from .config import config
from .cookies_manager import cookies_manager

logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理器，使用yt-dlp下载视频和提取音频"""
    
    def __init__(self):
        """
        初始化视频处理器
        """
        # 基础配置 - 增强反机器人检测配置
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,  # 强制只下载单个视频，不下载播放列表
            'prefer_ffmpeg': True,
            # 反机器人检测配置
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            },
            # 从配置文件获取增强选项（包括代理、cookies等）
            **config.get_enhanced_opts()
        }
        
        # 平台特定的处理策略
        # 现在支持抖音平台（需要配置cookies）
        self.platform_strategies = {
            'bilibili': self._get_bilibili_strategy,
            'xiaohongshu': self._get_xiaohongshu_strategy,
            'youtube': self._get_youtube_strategy,
            'tiktok': self._get_tiktok_strategy,
            'douyin': self._get_douyin_strategy,
        }
        
        # 视频下载配置 - 多平台兼容的智能格式选择策略
        self.video_opts = {
            **self.base_opts,
            'format': (
                # 全平台兼容的多层回退策略
                # 1. 优先尝试中等质量的合并格式
                'best[height<=720][filesize<100M]/'
                # 2. 分离格式自动合并 (B站等)
                'worstvideo[height>=360]+worstaudio[acodec!=none]/'
                'worstvideo+worstaudio/'
                # 3. 单独视频格式回退
                'best[height<=720]/'
                'best[height<=480]/'
                # 4. 最终兜底策略
                'worstvideo+bestaudio/'
                'worst'
            ),
            'outtmpl': '%(title)s.%(ext)s',
            'merge_output_format': 'mp4',
            # 添加更多兼容性选项
            'writesubtitles': False,
            'writeautomaticsub': False,
        }
        
        # 音频提取配置 - 兼容各平台的音频格式选择
        self.audio_opts = {
            **self.base_opts,
            'format': (
                # 音频格式选择策略
                'bestaudio[filesize<50M]/'  # 优先选择文件大小合理的最佳音频
                'bestaudio/'                # 然后选择最佳音频
                'best[filesize<50M]/'       # 如果没有纯音频，选择小文件的最佳格式
                'best'                      # 最后兜底选项
            ),
            'outtmpl': '%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    
    def _get_platform_from_url(self, url: str) -> str:
        """从URL识别平台"""
        if 'bilibili.com' in url:
            return 'bilibili'
        elif 'douyin.com' in url or 'v.douyin.com' in url:
            return 'douyin'
        elif 'xiaohongshu.com' in url:
            return 'xiaohongshu'
        elif 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'tiktok.com' in url:
            return 'tiktok'
        else:
            return 'generic'
    
    
    
    def _get_bilibili_strategy(self):
        """B站平台的格式选择策略"""
        return {
            'format': 'worstvideo[height>=360]+worstaudio/worstvideo+worstaudio/worst',
        }
    
    def _get_xiaohongshu_strategy(self):
        """小红书平台的格式选择策略"""
        return {
            'format': 'best[height<=720]/best',
        }
    
    def _get_youtube_strategy(self):
        """YouTube平台的格式选择策略 - 增强反机器人检测"""
        strategy = {
            'format': 'best[height<=1080]/best',
            # YouTube 特定的反机器人配置
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],  # 跳过某些可能触发检测的格式
                    'player_client': ['android', 'web'],  # 使用移动端客户端
                }
            },
            # 额外的请求头，专门针对 YouTube
            'http_headers': {
                **self.base_opts.get('http_headers', {}),
                'Referer': 'https://www.youtube.com/',
                'Origin': 'https://www.youtube.com',
                'X-YouTube-Client-Name': '1',
                'X-YouTube-Client-Version': '2.20231201.01.00',
            },
            # 更保守的重试策略
            'retries': 5,
            'fragment_retries': 5,
            'sleep_interval': max(2, config.request_sleep_interval),
            'max_sleep_interval': max(10, config.max_request_sleep_interval),
        }
        
        # 添加 YouTube 特定配置（如 cookies）
        youtube_config = config.get_youtube_config()
        strategy.update(youtube_config)
        
        return strategy
    
    def _get_tiktok_strategy(self):
        """TikTok平台的格式选择策略"""
        return {
            'format': 'best[height<=720]/best',
        }
    
    def _get_douyin_strategy(self):
        """抖音平台的格式选择策略 - 需要cookies支持"""
        return {
            'format': 'best[height<=720]/best',
            # 抖音特定的请求头
            'http_headers': {
                **self.base_opts.get('http_headers', {}),
                'Referer': 'https://www.douyin.com/',
                'Origin': 'https://www.douyin.com',
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
            },
            # 更保守的重试策略
            'retries': 5,
            'fragment_retries': 5,
            'sleep_interval': max(2, config.request_sleep_interval),
            'max_sleep_interval': max(10, config.max_request_sleep_interval),
        }
    
    def _get_optimized_opts(self, url: str, base_opts: dict) -> dict:
        """根据平台优化配置选项"""
        platform = self._get_platform_from_url(url)
        opts = base_opts.copy()
        
        # 集成cookies管理器 - 为所有平台尝试配置cookies
        cookies_config = cookies_manager.setup_platform_cookies(platform)
        if cookies_config:
            opts.update(cookies_config)
        
        if platform in self.platform_strategies:
            strategy = self.platform_strategies[platform]()
            # 合并 http_headers，确保平台特定的头部覆盖基础头部
            if 'http_headers' in strategy and 'http_headers' in opts:
                merged_headers = opts['http_headers'].copy()
                merged_headers.update(strategy['http_headers'])
                strategy['http_headers'] = merged_headers
            
            opts.update(strategy)
            logger.info(f"使用 {platform} 平台优化策略，配置了反机器人检测选项")
            
            # 对于不同平台的特殊提示
            if platform == 'youtube':
                logger.info("YouTube 配置：使用真实浏览器 User-Agent 和请求头")
                logger.info("YouTube 配置：启用重试机制和请求间隔")
            elif platform == 'douyin':
                cookies_file = cookies_manager.get_cookies_file(platform)
                if cookies_file:
                    logger.info("抖音配置：使用cookies文件进行身份验证")
                else:
                    logger.warning("抖音配置：未找到cookies文件，可能影响下载成功率")
                    logger.info("抖音提示：建议配置cookies文件以提高成功率")
        else:
            logger.info("使用通用策略")
        
        return opts
    
    async def download_video_and_audio(
        self, 
        url: str, 
        output_dir: Path, 
        extract_audio: bool = True, 
        keep_video: bool = True
    ) -> Dict[str, Optional[str]]:
        """
        下载视频和/或提取音频
        
        Args:
            url: 视频链接
            output_dir: 输出目录
            extract_audio: 是否提取音频
            keep_video: 是否保留视频文件
            
        Returns:
            包含文件路径的字典 {'video': path, 'audio': path}
        """
        try:
            # 边界情况检查
            if not extract_audio and not keep_video:
                raise ValueError("必须至少选择提取音频或保留视频中的一项")
            
            # 创建输出目录
            output_dir.mkdir(exist_ok=True)
            
            # 生成唯一的文件名前缀
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            
            result_files = {}
            
            logger.info(f"开始处理视频: {url}")
            logger.info(f"处理选项: extract_audio={extract_audio}, keep_video={keep_video}")
            
            import asyncio
            
            # 智能处理策略：如果同时需要视频和音频，优化处理方式
            if keep_video and extract_audio:
                # 策略1: 同时下载视频和音频（并行处理）
                logger.info("同时下载视频和音频...")
                video_task = self._download_video_only(url, output_dir, unique_id)
                audio_task = self._download_audio_only(url, output_dir, unique_id)
                
                video_result, audio_result = await asyncio.gather(
                    video_task, audio_task, return_exceptions=True
                )
                
                if not isinstance(video_result, Exception) and video_result:
                    result_files['video'] = video_result
                    logger.info(f"视频文件已保存: {video_result}")
                
                if not isinstance(audio_result, Exception) and audio_result:
                    result_files['audio'] = audio_result
                    logger.info(f"音频文件已保存: {audio_result}")
                
                # 完整的双向回退机制
                # 情况1: 音频失败但视频成功 -> 从视频提取音频
                if 'audio' not in result_files and 'video' in result_files:
                    logger.info("音频下载失败，正在从视频文件提取音频...")
                    audio_from_video = await self._extract_audio_from_video(
                        result_files['video'], output_dir, unique_id
                    )
                    if audio_from_video:
                        result_files['audio'] = audio_from_video
                        logger.info(f"从视频提取音频成功: {audio_from_video}")
                
                # 情况2: 视频失败但音频成功 -> 尝试重新下载视频或提供部分结果
                elif 'video' not in result_files and 'audio' in result_files:
                    logger.warning("视频下载失败但音频下载成功，尝试重新下载视频...")
                    # 重试视频下载一次
                    retry_video = await self._download_video_only(url, output_dir, unique_id + "_retry")
                    if retry_video:
                        result_files['video'] = retry_video
                        logger.info(f"重试视频下载成功: {retry_video}")
                    else:
                        logger.warning("视频重试下载也失败，将只返回音频文件")
                
                # 情况3: 两者都失败 -> 尝试下载视频然后提取音频
                elif 'video' not in result_files and 'audio' not in result_files:
                    logger.warning("视频和音频都下载失败，尝试应急方案...")
                    emergency_video = await self._download_video_only(url, output_dir, unique_id + "_emergency")
                    if emergency_video:
                        result_files['video'] = emergency_video
                        logger.info(f"应急视频下载成功: {emergency_video}")
                        # 从应急视频提取音频
                        emergency_audio = await self._extract_audio_from_video(
                            emergency_video, output_dir, unique_id + "_emergency"
                        )
                        if emergency_audio:
                            result_files['audio'] = emergency_audio
                            logger.info(f"从应急视频提取音频成功: {emergency_audio}")
                    else:
                        logger.error("所有下载尝试都失败了")
            
            elif keep_video:
                # 只下载视频 - 带重试机制
                logger.info("下载视频文件...")
                video_file = await self._download_video_only(url, output_dir, unique_id)
                if video_file:
                    result_files['video'] = video_file
                    logger.info(f"视频文件已保存: {video_file}")
                else:
                    # 视频下载失败，尝试重试一次
                    logger.warning("视频下载失败，尝试重新下载...")
                    retry_video = await self._download_video_only(url, output_dir, unique_id + "_retry")
                    if retry_video:
                        result_files['video'] = retry_video
                        logger.info(f"重试视频下载成功: {retry_video}")
                    else:
                        logger.error("视频下载和重试都失败了")
                        raise Exception("无法下载视频文件，请检查链接是否有效或稍后重试")
            
            elif extract_audio:
                # 只提取音频 - 智能回退机制
                logger.info("提取音频文件...")
                audio_file = await self._download_audio_only(url, output_dir, unique_id)
                if audio_file:
                    result_files['audio'] = audio_file
                    logger.info(f"音频文件已保存: {audio_file}")
                else:
                    # 直接音频提取失败，尝试下载视频然后提取音频
                    logger.info("直接音频提取失败，正在下载视频并从中提取音频...")
                    video_file = await self._download_video_only(url, output_dir, unique_id)
                    if video_file:
                        logger.info(f"视频下载成功: {video_file}")
                        audio_from_video = await self._extract_audio_from_video(
                            video_file, output_dir, unique_id
                        )
                        if audio_from_video:
                            result_files['audio'] = audio_from_video
                            logger.info(f"从视频提取音频成功: {audio_from_video}")
                            # 删除临时视频文件（用户只要音频）
                            try:
                                os.unlink(video_file)
                                logger.info(f"已删除临时视频文件: {video_file}")
                            except Exception as e:
                                logger.warning(f"删除临时视频文件失败: {e}")
                        else:
                            logger.error("从视频提取音频也失败了")
                    else:
                        logger.error("视频下载失败，无法提取音频")
            
            if not result_files:
                raise Exception("没有成功下载任何文件")
            
            return result_files
            
        except Exception as e:
            logger.error(f"处理视频失败: {str(e)}")
            raise Exception(f"处理视频失败: {str(e)}")
    
    async def _download_video_only(self, url: str, output_dir: Path, unique_id: str) -> Optional[str]:
        """只下载视频文件"""
        try:
            import asyncio
            
            logger.info(f"视频下载使用的URL: {url}")
            
            video_template = str(output_dir / f"video_{unique_id}.%(ext)s")
            video_opts = self._get_optimized_opts(url, self.video_opts)
            video_opts['outtmpl'] = video_template
            
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                await asyncio.to_thread(ydl.download, [url])
            
            # 查找下载的视频文件
            for ext in ['mp4', 'webm', 'mkv', 'avi', 'mov', 'flv']:
                potential_file = output_dir / f"video_{unique_id}.{ext}"
                if potential_file.exists():
                    return str(potential_file)
            
            return None
        except Exception as e:
            logger.error(f"下载视频失败: {e}")
            return None
    
    async def _download_audio_only(self, url: str, output_dir: Path, unique_id: str) -> Optional[str]:
        """只提取音频文件（使用yt-dlp直接提取）"""
        try:
            import asyncio
            
            logger.info(f"音频下载使用的URL: {url}")
            
            audio_template = str(output_dir / f"audio_{unique_id}.%(ext)s")
            audio_opts = self._get_optimized_opts(url, self.audio_opts)
            audio_opts['outtmpl'] = audio_template
            
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                await asyncio.to_thread(ydl.download, [url])
            
            # 查找提取的音频文件
            for ext in ['mp3', 'm4a', 'wav', 'aac', 'ogg']:
                potential_file = output_dir / f"audio_{unique_id}.{ext}"
                if potential_file.exists():
                    return str(potential_file)
            
            return None
        except Exception as e:
            logger.error(f"提取音频失败: {e}")
            return None
    
    async def _extract_audio_from_video(self, video_path: str, output_dir: Path, unique_id: str) -> Optional[str]:
        """从视频文件中提取音频（使用FFmpeg）"""
        try:
            import asyncio
            import subprocess
            
            audio_path = output_dir / f"audio_{unique_id}.mp3"
            
            # 使用FFmpeg从视频中提取音频
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn',  # 不处理视频流
                '-acodec', 'mp3',  # 音频编码器
                '-ab', '192k',  # 音频比特率
                '-ar', '44100',  # 采样率
                '-y',  # 覆盖输出文件
                str(audio_path)
            ]
            
            await asyncio.to_thread(subprocess.run, cmd, 
                                  capture_output=True, check=True)
            
            if audio_path.exists():
                return str(audio_path)
            
            return None
        except Exception as e:
            logger.error(f"从视频提取音频失败: {e}")
            return None
    
    async def download_and_convert(self, url: str, output_dir: Path) -> tuple[str, str]:
        """
        兼容性方法：下载视频并转换为音频格式
        保留此方法以兼容旧代码
        
        Args:
            url: 视频链接
            output_dir: 输出目录
            
        Returns:
            (音频文件路径, 视频标题)
        """
        try:
            # 获取视频信息
            info = self.get_video_info(url)
            video_title = info.get('title', 'unknown')
            
            # 只提取音频
            result = await self.download_video_and_audio(
                url, output_dir, extract_audio=True, keep_video=False
            )
            
            audio_file = result.get('audio')
            if not audio_file:
                raise Exception("音频提取失败")
            
            return audio_file, video_title
            
        except Exception as e:
            logger.error(f"下载转换失败: {str(e)}")
            raise Exception(f"下载转换失败: {str(e)}")
    
    def get_video_info(self, url: str) -> dict:
        """
        获取视频信息
        
        Args:
            url: 视频链接
            
        Returns:
            视频信息字典
        """
        try:
            logger.info(f"开始获取视频信息: {url}")
            platform = self._get_platform_from_url(url)
            logger.info(f"检测到平台: {platform}")
            
            # 获取优化后的选项，只用于信息提取
            opts = self._get_optimized_opts(url, self.base_opts)
            
            # 对于 YouTube，添加特殊的错误处理提示
            if platform == 'youtube':
                logger.info("正在使用增强的反机器人检测配置获取 YouTube 视频信息...")
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            logger.info(f"成功获取视频信息: {info.get('title', '未知标题')}")
            
            return {
                'title': info.get('title', '未知标题'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', '未知作者'),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'description': info.get('description', ''),
                'upload_date': info.get('upload_date', ''),
                'thumbnail': info.get('thumbnail', ''),
                'webpage_url': info.get('webpage_url', url),
                'extractor': info.get('extractor', ''),
                'id': info.get('id', ''),
                'formats': len(info.get('formats', []))
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"获取视频信息失败: {error_msg}")
            
            # 为 YouTube 机器人检测错误提供更友好的错误信息
            if 'youtube' in url.lower() and ('Sign in to confirm' in error_msg or 'bot' in error_msg.lower()):
                friendly_msg = ("YouTube 检测到机器人行为。可能的解决方案：\n"
                              "1. 稍等几分钟后重试\n"
                              "2. 检查服务器网络环境\n"
                              "3. 考虑使用代理服务器\n"
                              f"原始错误: {error_msg}")
                raise Exception(friendly_msg)
            else:
                raise Exception(f"获取视频信息失败: {error_msg}")
