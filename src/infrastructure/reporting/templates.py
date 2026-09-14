"""
HTML模板模块
使用Jinja2加载外部HTML模板文件
"""

import asyncio
import os
import threading

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ...utils.logger import logger


class HTMLTemplates:
    """HTML模板管理类"""

    AVAILABLE_TEMPLATES = [
        "ATRI",
        "BlueArchive",
        "scrapbook",
        "retro_futurism",
        "HatsuneMiku",
        "hack",
        "spring_festival",
        "simple",
        "format",
    ]

    def __init__(self, config_manager):
        """初始化Jinja2环境"""
        self.config_manager = config_manager
        # 设置模板根目录
        self.base_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.platform_base_dir = os.path.join(
            os.path.dirname(__file__), "platform_templates"
        )
        # 缓存不同模板的Jinja2环境（多线程安全）
        self._envs = {}
        self._env_lock = threading.Lock()
        self._active_template_override: str | None = None

    def set_template_override(self, template_name: str | None):
        """临时覆盖当前使用的模板（用于模拟/测试/单次指定模板）"""
        self._active_template_override = template_name

    def select_fresh_template(self) -> str:
        """如果开启了随机模板，抽取一个模板作为当前批次的主题"""
        if self._active_template_override:
            return self._active_template_override
        if self.config_manager.get_random_report_template_enabled():
            import random

            selected = random.choice(self.AVAILABLE_TEMPLATES)
            self._active_template_override = selected
            logger.info(f"[群分析插件] 开启了随机模板模式，本次选用模板: {selected}")
            return selected
        return self.config_manager.get_report_template()

    def get_current_template_name(self) -> str:
        if self._active_template_override:
            return self._active_template_override
        if self.config_manager.get_random_report_template_enabled():
            return self.select_fresh_template()
        return self.config_manager.get_report_template()

    def _get_env_sync(self) -> Environment:
        """获取当前配置的模板环境（同步版本，供 asyncio.to_thread 调用）"""
        template_name = self.get_current_template_name()

        # 如果环境已缓存且配置未变（使用锁保证多线程安全）
        with self._env_lock:
            env = self._envs.get(template_name)
            if env is not None:
                return env

        template_dir = os.path.join(self.base_dir, template_name)
        if not os.path.exists(template_dir):
            logger.warning(f"模板目录不存在: {template_dir}，回退到 scrapbook")
            template_dir = os.path.join(self.base_dir, "scrapbook")

        env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # 使用双重检查锁定，避免在高并发下重复创建相同 template_name 的 env
        with self._env_lock:
            existing = self._envs.get(template_name)
            if existing is not None:
                return existing
            self._envs[template_name] = env

        return env

    async def _get_env_async(self) -> Environment:
        """获取当前配置的模板环境（异步版本）"""
        return await asyncio.to_thread(self._get_env_sync)

    def _get_env(self) -> Environment:
        """获取当前配置的模板环境（同步版本，向后兼容）"""
        return self._get_env_sync()

    def _read_template_file_sync(self, filename: str) -> str:
        """同步读取模板文件内容"""
        with open(filename, encoding="utf-8") as f:
            return f.read()

    async def get_image_template_async(self) -> str:
        """获取图片报告的HTML模板（异步版本，返回原始模板字符串）"""
        try:
            env = await self._get_env_async()
            template = env.get_template("image_template.html")
            if template.filename is None:
                logger.error("图片模板路径为空")
                return ""
            return await asyncio.to_thread(
                self._read_template_file_sync, template.filename
            )
        except Exception as e:
            logger.error(f"加载图片模板失败: {e}")
            return ""

    def get_image_template(self) -> str:
        """获取图片报告的HTML模板（同步版本，向后兼容）"""
        try:
            env = self._get_env()
            template = env.get_template("image_template.html")
            if template.filename is None:
                logger.error("图片模板路径为空")
                return ""
            with open(template.filename, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"加载图片模板失败: {e}")
            return ""

    def render_template(self, template_name: str, **kwargs) -> str:
        """渲染指定的模板文件

        Args:
            template_name: 模板文件名
            **kwargs: 传递给模板的变量

        Returns:
            渲染后的HTML字符串
        """
        try:
            env = self._get_env()
            template = env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"渲染模板 {template_name} 失败: {e}")
            return ""

    def render_platform_template(
        self, platform_name: str, template_name: str, **kwargs
    ) -> str:
        """渲染与报告主题解耦的平台专用模板。"""
        try:
            template_dir = os.path.join(self.platform_base_dir, platform_name)
            env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=select_autoescape(["html", "xml"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            return env.get_template(template_name).render(**kwargs)
        except Exception as e:
            logger.error(f"渲染平台模板 {platform_name}/{template_name} 失败: {e}")
            return ""
