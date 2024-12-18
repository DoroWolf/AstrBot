import asyncio, aiohttp
import pytest
import os

from tests.mocks.qq_official import MockQQOfficialMessage
from tests.mocks.onebot import MockOneBotMessage

from astrbot.bootstrap import AstrBotBootstrap
from model.platform.qq_official import QQOfficial
from model.platform.qq_aiocqhttp import AIOCQHTTP
from model.provider.openai_official import ProviderOpenAIOfficial
from type.astrbot_message import *
from type.message_event import *
from util.log import LogManager

from util.cmd_config import QQOfficialPlatformConfig, AiocqhttpPlatformConfig

logger = LogManager.GetLogger(log_name='astrbot')
pytest_plugins = ('pytest_asyncio',)

os.environ['TEST_MODE'] = 'on'
bootstrap = AstrBotBootstrap()

llm_config = bootstrap.context.config_helper.llm[0]
llm_config.api_base = os.environ['OPENAI_API_BASE']
llm_config.key = [os.environ['OPENAI_API_KEY']]
llm_config.model_config.model = os.environ['LLM_MODEL']
llm_config.model_config.max_tokens = 1000
asyncio.run(bootstrap.run())
llm_provider = ProviderOpenAIOfficial(llm_config, bootstrap.db_helper)
bootstrap.message_handler.provider = llm_provider
bootstrap.config_helper.wake_prefix = ["/"]
bootstrap.config_helper.admins_id = ["905617992"]

for p_config in bootstrap.context.config_helper.platform:
    if isinstance(p_config, QQOfficialPlatformConfig):
        qq_official = QQOfficial(bootstrap.context, bootstrap.message_handler, p_config)
    elif isinstance(p_config, AiocqhttpPlatformConfig):
        aiocqhttp = AIOCQHTTP(bootstrap.context, bootstrap.message_handler, p_config)

class TestBasicMessageHandle():
    @pytest.mark.asyncio
    async def test_qqofficial_group_message(self):
        group_message = MockQQOfficialMessage().create_random_group_message()
        abm = qq_official._parse_from_qqofficial(group_message, MessageType.GROUP_MESSAGE)
        ret = await qq_official.handle_msg(abm)
        print(ret)
        
    @pytest.mark.asyncio
    async def test_qqofficial_guild_message(self):
        guild_message = MockQQOfficialMessage().create_random_guild_message()
        abm = qq_official._parse_from_qqofficial(guild_message, MessageType.GUILD_MESSAGE)
        ret = await qq_official.handle_msg(abm)
        print(ret)
    
    @pytest.mark.asyncio
    async def test_aiocqhttp_group_message(self):
        event = MockOneBotMessage().create_random_group_message()
        abm = aiocqhttp.convert_message(event)
        ret = await aiocqhttp.handle_msg(abm)
        print(ret)

    @pytest.mark.asyncio
    async def test_aiocqhttp_direct_message(self):
        event = MockOneBotMessage().create_random_direct_message()
        abm = aiocqhttp.convert_message(event)
        ret = await aiocqhttp.handle_msg(abm)
        print(ret)
        
class TestInteralCommandHandle():
    def create(self, text: str):
        event = MockOneBotMessage().create_msg(text)
        abm = aiocqhttp.convert_message(event)
        return abm
    
    async def fast_test(self, text: str):
        abm = self.create(text)
        ret = await aiocqhttp.handle_msg(abm)
        print(f"Command: {text}, Result: {ret.result_message}")
        return ret
    
    @pytest.mark.asyncio
    async def test_config_save(self):
        abm = self.create("/websearch on")
        ret = await aiocqhttp.handle_msg(abm)
        assert bootstrap.context.config_helper.llm_settings.web_search \
            == bootstrap.config_helper.get("llm_settings")['web_search']
    
    @pytest.mark.asyncio
    async def test_websearch(self):
        await self.fast_test("/websearch")
        await self.fast_test("/websearch on")
        await self.fast_test("/websearch off")
    
    @pytest.mark.asyncio
    async def test_help(self):
        await self.fast_test("/help")
        
    @pytest.mark.asyncio
    async def test_myid(self):
        await self.fast_test("/myid")
        
    @pytest.mark.asyncio
    async def test_wake(self):
        await self.fast_test("/wake")
        await self.fast_test("/wake #")
        assert "#" in bootstrap.context.config_helper.wake_prefix 
        assert "#" in bootstrap.context.config_helper.get("wake_prefix")
        await self.fast_test("#wake /")
        
    @pytest.mark.asyncio
    async def test_sleep(self):
        await self.fast_test("/provider")
    
    @pytest.mark.asyncio
    async def test_update(self):
        await self.fast_test("/update")
    
    @pytest.mark.asyncio
    async def test_t2i(self):
        if not bootstrap.context.config_helper.t2i:
            abm = self.create("/t2i")
            await aiocqhttp.handle_msg(abm)
        await self.fast_test("/help")

    @pytest.mark.asyncio
    async def test_plugin(self):
        pname = "astrbot_plugin_bilibili"
        url = f"https://github.com/Soulter/{pname}"
        await self.fast_test("/plugin")
        await self.fast_test(f"/plugin l")
        await self.fast_test(f"/plugin i {url}")
        await self.fast_test(f"/plugin u {url}")
        await self.fast_test(f"/plugin d {pname}")
        
    @pytest.mark.asyncio
    async def test_llm(self):
        await self.fast_test("/reset")        
        os.environ["TEST_LLM"] = "on"
        ret = await llm_provider.text_chat("Just reply `ok`", "test")
        print(ret)
        event = MockOneBotMessage().create_msg("Just reply `ok`")
        abm = aiocqhttp.convert_message(event)
        ret = await aiocqhttp.handle_msg(abm)
        print(ret)
        os.environ["TEST_LLM"] = "off"
        await self.fast_test("/reset")
        await self.fast_test("/status")
        await self.fast_test("/his")
        await self.fast_test("/switch")
        await self.fast_test("/set")
        await self.fast_test("/set list")
        await self.fast_test("/unset")

BASE_URL = "http://0.0.0.0:6185/api"
class TestHTTPServer:
    
    async def get_url(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json(), response.status
            
    async def post_url(self, url, data):
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                return await response.json(), response.status
        
    @pytest.mark.asyncio
    async def test_config(self):
        configs, status = await self.get_url(f"{BASE_URL}/config/get")
        assert status == 200
        assert 'data' in configs and 'metadata' in configs['data'] \
            and 'config' in configs['data']
        config = configs['data']['config']
        # test post config
        await self.post_url(f"{BASE_URL}/config/astrbot/update", config)
        # text post config with invalid data
        assert 'rate_limit' in config['platform_settings']
        config['platform_settings']['rate_limit'] = "invalid"
        ret, status = await self.post_url(f"{BASE_URL}/config/astrbot/update", config)
        assert status == 200
        assert 'status' in ret and ret['status'] == 'error'
    
    @pytest.mark.asyncio
    async def test_update(self):
        _, status = await self.get_url(f"{BASE_URL}/update/check")
        assert status == 200
        
    @pytest.mark.asyncio
    async def test_stats(self):
        _, status = await self.get_url(f"{BASE_URL}/stat/get")
        _, status = await self.get_url(f"{BASE_URL}/stat/version")
        _, status = await self.get_url(f"{BASE_URL}/stat/start-time")
        assert status == 200
    
    @pytest.mark.asyncio
    async def test_plugins(self):
        pname = "astrbot_plugin_bilibili"
        url = f"https://github.com/Soulter/{pname}"

        _, status = await self.get_url(f"{BASE_URL}/plugin/get")

        # test install plugin
        _, status = await self.post_url(f"{BASE_URL}/plugin/install", {
            "url": url
        })
        
        # test uninstall plugin
        _, status = await self.post_url(f"{BASE_URL}/plugin/uninstall", {
            "name": pname
        })
        
        assert status == 200
        
        bootstrap.context.running = False
