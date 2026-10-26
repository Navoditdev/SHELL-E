import asyncio
from pathlib import Path
import tempfile
import unittest

from shell_e.config import Config
from shell_e.execution import CommandRequest, execute_command
from shell_e.safety import workspace_path
from shell_e.tools import ToolContext, run_tool


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.approvals = []

        async def reject(request):
            self.approvals.append(request)
            return False

        self.ctx = ToolContext(Config(self.root), self.root, reject)

    async def test_workspace_blocks_traversal_and_symlink_escape(self):
        (self.root / 'outside').symlink_to('/etc')
        for path in ('..', 'outside/passwd'):
            with self.assertRaisesRegex(ValueError, 'outside'):
                workspace_path(self.root, self.root, path)
        self.assertEqual(workspace_path(self.root, self.root, '.'), self.root)

    async def test_file_tools_and_persistent_cwd(self):
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'a.py').write_text('hello')
        self.assertEqual(await run_tool('find_files', {'path': '.', 'pattern': '*.py'}, self.ctx),
                         {'matches': ['nested/a.py'], 'capped': False})
        await run_tool('change_directory', {'path': 'nested'}, self.ctx)
        self.assertEqual(self.ctx.cwd, nested)
        self.assertEqual(await run_tool('read_file', {'path': 'a.py'}, self.ctx), {'content': 'hello'})
        listing = await run_tool('list_directory', {'path': '.'}, self.ctx)
        self.assertEqual(listing['entries'][0]['name'], 'a.py')

    async def test_rejection_prevents_execution_and_invalid_args_prevent_approval(self):
        for timeout in (-1, True, '100'):
            with self.assertRaises(ValueError):
                await run_tool('execute_command', {'command': 'pwd', 'explanation': 'test', 'timeoutMs': timeout}, self.ctx)
        self.assertEqual(self.approvals, [])
        result = await run_tool('execute_command', {'command': 'touch forbidden', 'explanation': 'test'}, self.ctx)
        self.assertTrue(result['denied'])
        self.assertFalse((self.root / 'forbidden').exists())
        self.assertEqual(len(self.approvals), 1)
        with self.assertRaisesRegex(ValueError, 'Unknown tool'):
            await run_tool('invented_tool', {}, self.ctx)

    async def test_large_files_and_fifos_are_rejected(self):
        (self.root / 'large').write_bytes(b'x' * 16001)
        import os
        os.mkfifo(self.root / 'fifo')
        for name in ('large', 'fifo'):
            with self.assertRaises(ValueError):
                await run_tool('read_file', {'path': name}, self.ctx)

    async def test_runner_output_exit_and_live_events(self):
        events = []
        result = await execute_command(CommandRequest('printf hello; printf failure >&2; exit 7', self.root, '', 1000),
                                       on_output=lambda stream, text: events.append((stream, text)))
        self.assertEqual(result['stdout'], 'hello')
        self.assertEqual(result['stderr'], 'failure')
        self.assertEqual(result['exitCode'], 7)
        self.assertIn(('stdout', 'hello'), events)

    async def test_timeout_kills_children(self):
        result = await execute_command(CommandRequest('sleep 0.2; touch late', self.root, '', 30))
        self.assertTrue(result['timedOut'])
        await asyncio.sleep(0.25)
        self.assertFalse((self.root / 'late').exists())

    async def test_cancellation_kills_children(self):
        task = asyncio.create_task(execute_command(CommandRequest('sleep 0.2; touch late', self.root, '', 2000)))
        await asyncio.sleep(0.03)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.25)
        self.assertFalse((self.root / 'late').exists())

    async def test_output_limit_and_background_cleanup(self):
        result = await execute_command(CommandRequest('yes output', self.root, '', 1000), max_output_bytes=100)
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['stdout'].encode()), 100)
        result = await execute_command(CommandRequest('sleep 10 & printf done', self.root, '', 1000))
        self.assertEqual(result['stdout'], 'done')
        self.assertFalse(result['timedOut'])
