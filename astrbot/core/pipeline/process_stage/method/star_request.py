from ...context import PipelineContext
from ..stage import Stage
from typing import Dict, Any, List, AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core import logger
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core.star.star import star_map
import traceback

class StarRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.curr_provider = ctx.plugin_manager.context.get_using_provider()
        self.prompt_prefix = ctx.astrbot_config['provider_settings']['prompt_prefix']
        self.identifier = ctx.astrbot_config['provider_settings']['identifier']
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        activated_handlers: List[StarHandlerMetadata] = event.get_extra("activated_handlers")
        handlers_parsed_params: Dict[str, Dict[str, Any]] = event.get_extra("handlers_parsed_params")
        if not handlers_parsed_params:
            handlers_parsed_params = {}
        for handler in activated_handlers:
            params = handlers_parsed_params.get(handler.handler_full_name, {})
            try:
                if handler.handler_module_str not in star_map:
                    # 孤立无援的 star handler 
                    continue
                
                logger.debug(f"执行 Star Handler {handler.handler_full_name}")
                wrapper = self._call_handler(self.ctx, event, handler.handler, **params)
                async for ret in wrapper:
                    yield ret
                event.clear_result() # 清除上一个 handler 的结果
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(f"Star {handler.handler_full_name} handle error: {e}")
                ret = f":(\n\n在调用插件 {star_map.get(handler.handler_module_str).name} 的处理函数 {handler.handler_name} 时出现异常：{e}"
                event.set_result(MessageEventResult().message(ret))
                yield
                event.clear_result()
                event.stop_event()