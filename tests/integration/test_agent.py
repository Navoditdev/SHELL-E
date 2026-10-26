import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from shell_e.agent import Agent
from shell_e.bridge import Bridge
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

    async def test_bridge_approval_ids_rejection_and_cancellation(self):
        async def chat(*_):
            return {'role': 'assistant', 'content': '', 'tool_calls': [
                {'function': {'name': 'execute_command', 'arguments': {'command': 'touch forbidden', 'explanation': 'test'}}},
                {'function': {'name': 'execute_command', 'arguments': {'command': 'touch second', 'explanation': 'test'}}}]}

        bridge = Bridge(Config(self.root), self.events.append, chat)
        await bridge.handle({'type': 'prompt', 'text': 'test'})
        await asyncio.sleep(0)
        approval_id = bridge.approval_id
        self.assertIsNotNone(approval_id)
        await bridge.handle({'type': 'approval', 'id': 'stale', 'approved': True})
        self.assertFalse(bridge.approval.done())
        await bridge.handle({'type': 'approval', 'id': approval_id, 'approved': False})
        task = bridge.task
        await task
        self.assertFalse((self.root / 'forbidden').exists())
        self.assertFalse((self.root / 'second').exists())
        self.assertEqual(bridge.agent.messages[-1]['role'], 'tool')
        await bridge.handle({'type': 'prompt', 'text': 'again'})
        await asyncio.sleep(0)
        task = bridge.task
        await bridge.handle({'type': 'cancel'})
        await task
        self.assertIsNone(bridge.approval)
        self.assertFalse(bridge.agent.busy)
        self.assertEqual(self.events[-1]['type'], 'done')

    async def test_bridge_executes_only_after_approval(self):
        turns = 0

        async def chat(*_):
            nonlocal turns
            turns += 1
            if turns == 1:
                return {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'function': {'name': 'execute_command', 'arguments': {'command': 'printf approved', 'explanation': 'test'}}}]}
            return {'role': 'assistant', 'content': 'Done'}

        bridge = Bridge(Config(self.root), self.events.append, chat)
        await bridge.handle({'type': 'prompt', 'text': 'test'})
        await asyncio.sleep(0)
        self.assertFalse(any(e['type'] == 'output' for e in self.events))
        await bridge.handle({'type': 'approval', 'id': bridge.approval_id, 'approved': True})
        await bridge.task
        self.assertTrue(any(e.get('text') == 'approved' for e in self.events))

    async def test_bridge_subprocess_startup_cd_and_shutdown(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'shell_e.bridge', stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, 'SHELL_E_WORKSPACE': str(self.root)},
        )
        try:
            ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 2))
            self.assertEqual(ready['type'], 'ready')
            (self.root / 'nested').mkdir()
            process.stdin.write(b'{"type":"cd","path":"nested"}\n')
            await process.stdin.drain()
            ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 2))
            self.assertEqual(ready['cwd'], str(self.root / 'nested'))
            process.stdin.write(b'{"type":"shutdown"}\n')
            await process.stdin.drain()
            await asyncio.wait_for(process.wait(), 2)
            self.assertEqual(process.returncode, 0, (await process.stderr.read()).decode())
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


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
