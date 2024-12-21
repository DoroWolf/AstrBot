import traceback
from typing import Union, AsyncGenerator
from ...context import PipelineContext
from ..stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageEventResult, ResultContentType
from astrbot.core.message.components import Image
from astrbot.core import logger
from astrbot.core.utils.metrics import Metric
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.star.star_handler import star_handlers_registry, EventType

class LLMRequestSubStage(Stage):
    
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        req: ProviderRequest = None
        
        provider = self.ctx.plugin_manager.context.get_using_provider()
        if event.get_extra("provider_request"):
            req = event.get_extra("provider_request")
            assert isinstance(req, ProviderRequest), "provider_request 必须是 ProviderRequest 类型。"
        else:
            req = ProviderRequest(prompt="", image_urls=[])
            if self.ctx.astrbot_config['provider_settings']['wake_prefix']:
                if not event.message_str.startswith(self.ctx.astrbot_config['provider_settings']['wake_prefix']):
                    return
            req.prompt = event.message_str[len(self.ctx.astrbot_config['provider_settings']['wake_prefix']):]
            req.func_tool = self.ctx.plugin_manager.context.get_llm_tool_manager()
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    image_url = comp.url if comp.url else comp.file
                    req.image_urls.append(image_url)
            req.session_id = event.session_id
            event.set_extra("provider_request", req)
            session_provider_context = provider.session_memory.get(event.session_id)
            req.contexts = session_provider_context if session_provider_context else []
            
        # 执行请求 LLM 前事件。
        # 装饰 system_prompt 等功能
        handlers = star_handlers_registry.get_handlers_by_event_type(EventType.OnLLMRequestEvent)
        for handler in handlers:
            try:
                await handler.handler(event, req)
            except BaseException:
                logger.error(traceback.format_exc())
        
        try:
            logger.debug(f"请求 LLM：{req.__dict__}")
            llm_response = await provider.text_chat(**req.__dict__) # 请求 LLM
            await Metric.upload(llm_tick=1, model_name=provider.get_model(), provider_type=provider.meta().type)

            if llm_response.role == 'assistant':
                # text completion
                event.set_result(MessageEventResult().message(llm_response.completion_text)
                                 .set_result_content_type(ResultContentType.LLM_RESULT))
            elif llm_response.role == 'tool':
                # function calling
                function_calling_result = {}
                for func_tool_name, func_tool_args in zip(llm_response.tools_call_name, llm_response.tools_call_args):
                    func_tool = req.func_tool.get_func(func_tool_name)
                    logger.info(f"调用工具函数：{func_tool_name}，参数：{func_tool_args}")
                    try:
                        # 尝试调用工具函数
                        wrapper = self._call_handler(self.ctx, event, func_tool.handler, **func_tool_args)
                        async for resp in wrapper:
                            if resp is not None:
                                function_calling_result[func_tool_name] = resp
                            else:
                                yield
                        event.clear_result() # 清除上一个 handler 的结果
                    except BaseException as e:
                        logger.warning(traceback.format_exc())
                        function_calling_result[func_tool_name] = "When calling the function, an error occurred: " + str(e)
                if function_calling_result:
                    # 工具返回 LLM 资源。比如 RAG、网页 得到的相关结果等。
                    # 我们重新执行一遍这个 stage
                    req.func_tool = None # 暂时不支持递归工具调用
                    extra_prompt = "\n\nSystem executed some external tools for this task and here are the results:\n"
                    for tool_name, tool_result in function_calling_result.items():
                        extra_prompt += f"Tool: {tool_name}\nTool Result: {tool_result}\n"
                    req.prompt += extra_prompt
                    async for _ in self.process(event):
                        yield

        except BaseException as e:
            logger.error(traceback.format_exc())
            event.set_result(MessageEventResult().message("AstrBot 请求 LLM 资源失败：" + str(e)))
            return