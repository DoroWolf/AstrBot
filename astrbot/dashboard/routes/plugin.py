import traceback
import aiohttp
import uuid
from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import request
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

class PluginRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle, plugin_manager: PluginManager) -> None:
        super().__init__(context)
        self.routes = {
            '/plugin/get': ('GET', self.get_plugins),
            '/plugin/install': ('POST', self.install_plugin),
            '/plugin/install-upload': ('POST', self.install_plugin_upload),
            '/plugin/update': ('POST', self.update_plugin),
            '/plugin/uninstall': ('POST', self.uninstall_plugin),
            '/plugin/market_list': ('GET', self.get_online_plugins)
        }
        self.core_lifecycle = core_lifecycle
        self.plugin_manager = plugin_manager
        self.register_routes()
    
    async def get_online_plugins(self):
        url = "https://soulter.github.io/AstrBot_Plugins_Collection/plugins.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    result = await response.json()
            return Response().ok(result).__dict__
        except Exception as e:
            logger.error(f"获取插件列表失败：{e}")
            return Response().error(str(e)).__dict__
    
    async def get_plugins(self):
        _plugin_resp = []
        for plugin in self.plugin_manager.context.get_all_stars():
            _t = {
                "name": plugin.name,
                "repo": '' if plugin.repo is None else plugin.repo,
                "author": plugin.author,
                "desc": plugin.desc,
                "version": plugin.version,
                "reserved": plugin.reserved
            }
            _plugin_resp.append(_t)
        return Response().ok(_plugin_resp).__dict__
        
    async def install_plugin(self):
        post_data = await request.json
        repo_url = post_data["url"]
        try:
            logger.info(f"正在安装插件 {repo_url}")
            await self.plugin_manager.install_plugin(repo_url)
            self.core_lifecycle.restart()
            logger.info(f"安装插件 {repo_url} 成功。")
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        
    async def install_plugin_upload(self):
        try:
            file = await request.files
            file = file['file']
            logger.info(f"正在安装用户上传的插件 {file.filename}")
            file_path = f"data/temp/{uuid.uuid4()}.zip"
            await file.save(file_path)
            self.plugin_manager.install_plugin_from_file(file_path)
            logger.info(f"安装插件 {file.filename} 成功")
            self.core_lifecycle.restart()
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        
    async def uninstall_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            logger.info(f"正在卸载插件 {plugin_name}")
            self.plugin_manager.uninstall_plugin(plugin_name)
            logger.info(f"卸载插件 {plugin_name} 成功")
            return Response().ok(None, "卸载成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        
    async def update_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            logger.info(f"正在更新插件 {plugin_name}")
            await self.plugin_manager.update_plugin(plugin_name)
            self.core_lifecycle.restart()
            logger.info(f"更新插件 {plugin_name} 成功，2秒后重启")
            return Response().ok(None, "更新成功，程序将在 2 秒内重启。").__dict__
        except Exception as e:
            logger.error(f"/api/extensions/update: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__