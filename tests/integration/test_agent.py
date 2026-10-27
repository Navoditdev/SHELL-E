import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from shell_e.agent import Agent
from shell_e.config import Config
from shell_e.ollama import OllamaChat
from shell_e.tools import ToolContext


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.events = []

    async def test_agent_returns_results_to_model_and_retains_history(self):
        calls = []

        async def chat(messages, tools, on_text):
            calls.append(messages)
            if len(calls) == 1:
                return {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'function': {'name': 'list_directory', 'arguments': {'path': '.'}}}]}
            if len(calls) == 2:
                self.assertEqual(messages[-1]['role'], 'tool')
                self.assertIn('entries', json.loads(messages[-1]['content']))
            return {'role': 'assistant', 'content': 'Done'}

        async def approve(_):
            return False

        agent = Agent(chat, ToolContext(Config(self.root), self.root, approve), self.events.append)
        await agent.run('List files')
        self.assertEqual(len(agent.messages), 4)
        await agent.run('Hello')
        self.assertEqual(len(agent.messages), 6)

class FakeResponse:
    status_code = 200

    def __init__(self, parts):
        self.parts = parts

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def aiter_lines(self):
        for part in self.parts:
            yield json.dumps(part)

    async def aread(self):
        return b'missing model'


class OllamaTests(unittest.IsolatedAsyncioTestCase):
    def client(self, response):
        class FakeClient:
            def __init__(self, **_):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            def stream(self, *_, **kwargs):
                self.request = kwargs
                return response
        return FakeClient

    async def test_stream_text_and_tool_calls(self):
        response = FakeResponse([
            {'message': {'content': 'Hello ', 'thinking': 'reason'}},
            {'message': {'content': 'world', 'tool_calls': [{'function': {'name': 'read_file', 'arguments': {'path': 'a'}}}]}},
            {'done': True},
        ])
        chunks = []
        message = await OllamaChat('http://localhost', 'test', self.client(response))([], [], chunks.append)
        self.assertEqual(message['content'], 'Hello world')
        self.assertEqual(message['thinking'], 'reason')
        self.assertEqual(message['tool_calls'][0]['function']['name'], 'read_file')
        self.assertEqual(chunks, ['Hello ', 'world'])

    async def test_http_errors_and_incomplete_streams(self):
        response = FakeResponse([])
        response.status_code = 404
        with self.assertRaisesRegex(RuntimeError, '404'):
            await OllamaChat('http://localhost', 'test', self.client(response))([], [], lambda _: None)
        response = FakeResponse([{'message': {'content': 'partial'}}])
        with self.assertRaisesRegex(RuntimeError, 'before completion'):
            await OllamaChat('http://localhost', 'test', self.client(response))([], [], lambda _: None)
