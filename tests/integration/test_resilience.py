import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from shell_e.agent import Agent
from shell_e.config import Config
from shell_e.messages import assistant_message
from shell_e.ollama import OllamaChat
from shell_e.tools import ToolContext
from tests.integration import test_agent as fixtures


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.events = []

    async def test_history_discards_whole_old_turns_and_keeps_tool_pairs(self):
        async def chat(*_):
            return {'role': 'assistant', 'content': 'new response'}

        async def approve(_):
            return False

        config = replace(Config(self.root), max_history_chars=600)
        agent = Agent(chat, ToolContext(config, self.root, approve), self.events.append)
        agent.messages = [
            {'role': 'user', 'content': 'x' * 500},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'read_file', 'arguments': {'path': 'a'}}}]},
            {'role': 'tool', 'tool_name': 'read_file', 'content': 'old'},
            {'role': 'assistant', 'content': 'finished'},
        ]
        await agent.run('new task')
        self.assertEqual(agent.messages[0], {'role': 'user', 'content': 'new task'})
        self.assertTrue(any('Older' in event.get('text', '') for event in self.events))

    async def test_current_task_budget_fails_cleanly(self):
        async def chat(*_):
            self.fail('Over-budget input should not reach the model')

        async def approve(_):
            return False

        agent = Agent(chat, ToolContext(replace(Config(self.root), max_history_chars=200), self.root, approve), self.events.append)
        with self.assertRaisesRegex(ValueError, 'conversation budget'):
            await agent.run('x' * 500)
        self.assertFalse(agent.busy)

    async def test_large_tool_results_are_shortened_for_model_but_not_ui(self):
        (self.root / 'file').write_text('x' * 10000)
        turns = 0

        async def chat(messages, *_):
            nonlocal turns
            turns += 1
            if turns == 1:
                return {'role': 'assistant', 'content': '', 'thinking': 'reason', 'tool_calls': [
                    {'function': {'name': 'read_file', 'arguments': {'path': 'file'}}}]}
            result = json.loads(messages[-1]['content'])
            self.assertTrue(result['truncatedForModel'])
            self.assertLess(len(messages[-1]['content']), 6000)
            return {'role': 'assistant', 'content': 'done'}

        async def approve(_):
            return False

        agent = Agent(chat, ToolContext(Config(self.root), self.root, approve), self.events.append)
        await agent.run('read file')
        result = next(e['result'] for e in self.events if e['type'] == 'result')
        self.assertEqual(len(result['content']), 10000)
        self.assertFalse(any('thinking' in m for m in agent.messages))

    async def test_malformed_tool_calls_never_reach_execution(self):
        async def chat(*_):
            return {'role': 'assistant', 'content': '', 'tool_calls': [{'function': None}]}

        async def approve(_):
            self.fail('Malformed calls must never request approval')

        agent = Agent(chat, ToolContext(Config(self.root), self.root, approve), self.events.append)
        with self.assertRaisesRegex(ValueError, 'function name'):
            await agent.run('test')
        self.assertEqual(len(agent.messages), 1)
        self.assertFalse(agent.busy)

    def test_tool_argument_normalization(self):
        result = assistant_message({'role': 'assistant', 'tool_calls': [
            {'function': {'name': 'read_file', 'arguments': '{"path":"a"}'}}]})
        self.assertEqual(result['tool_calls'][0]['function']['arguments'], {'path': 'a'})
        for args in ('{bad', '[]', [], None):
            with self.assertRaises(ValueError):
                assistant_message({'role': 'assistant', 'tool_calls': [
                    {'function': {'name': 'read_file', 'arguments': args}}]})

    async def test_network_errors_have_actionable_message(self):
        class Offline:
            def __init__(self, **_):
                pass

            async def __aenter__(self):
                raise OSError('connection refused')

            async def __aexit__(self, *_):
                pass
        with self.assertRaisesRegex(RuntimeError, 'ollama serve'):
            await OllamaChat('http://localhost:11434', 'test', Offline)([], [], lambda _: None)

    async def test_invalid_stream_and_unsupported_model(self):
        client = fixtures.OllamaTests().client
        for part in ([], {'message': []}, {'message': {'content': 123}}, {'message': {'tool_calls': 'bad'}}):
            with self.assertRaises(RuntimeError):
                await OllamaChat('http://localhost', 'test', client(fixtures.FakeResponse([part])))([], [], lambda _: None)
        response = fixtures.FakeResponse([])
        response.status_code = 400

        async def body():
            return b'model does not support tools'

        response.aread = body
        with self.assertRaisesRegex(RuntimeError, 'does not support tool calling'):
            await OllamaChat('http://localhost', 'test', client(response))([], [], lambda _: None)
