import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/codex-dsh-chat/scripts'))
import chat


class Fake:
    sends = 0
    fail = False
    cwd = '/project'

    def close(self):
        pass

    def identity(self, ident):
        return {'id': ident, 'cwd': self.cwd}

    def send(self, ident, text, request_id):
        Fake.sends += 1
        if Fake.fail:
            raise TimeoutError()
        return {'accepted': True}


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        for d in ['pairs', 'messages', 'locks']:
            chat.private_dir(self.state / d)
        self.pair = {'codex': {'id': '00000000-0000-0000-0000-000000000001', 'cwd': '/project'},
                     'dsh': {'id': 'session-00000000-0000-0000-0000-000000000002', 'cwd': '/project'}}
        chat.save(self.state/'pairs'/'test.json', self.pair)
        Fake.sends = 0
        Fake.fail = False
        Fake.cwd = '/project'

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, *extra):
        with patch.object(chat, 'client', return_value=Fake()), contextlib.redirect_stdout(io.StringIO()):
            chat.main(['--state-dir', str(self.state), 'send', '--pair', 'test', '--from', 'codex',
                       '--id', 'one', '--message', 'hello', *extra])

    def receipt(self):
        return json.loads((self.state/'messages'/'one.json').read_text())

    def test_duplicate_is_not_resent(self):
        self.send(); self.send()
        self.assertEqual(Fake.sends, 1)

    def test_same_id_changed_payload_rejected(self):
        self.send()
        with self.assertRaises(chat.BridgeError):
            self.send('--message', 'different')
        self.assertEqual(Fake.sends, 1)

    def test_timeout_unknown_and_no_retry(self):
        Fake.fail = True
        with self.assertRaises(TimeoutError):
            self.send()
        self.assertEqual(self.receipt()['state'], 'UNKNOWN')
        Fake.fail = False
        self.send()
        self.assertEqual(Fake.sends, 1)

    def test_workspace_drift_refused_before_send(self):
        Fake.cwd = '/other'
        with self.assertRaises(chat.BridgeError):
            self.send()
        self.assertEqual(Fake.sends, 0)

    def test_old_ack_or_user_echo_not_assistant_ack(self):
        self.send(); r = self.receipt()
        chat.observe(r, [{'id': 1, 'role': 'assistant', 'text': r['marker']},
                         {'id': 2, 'role': 'user', 'text': r['message']}], False)
        self.assertEqual(r['state'], 'DELIVERED_AWAITING_REPLY')
        self.assertIsNone(r['assistant_ack'])

    def test_correlated_ack_and_readback(self):
        self.send(); r = self.receipt()
        chat.observe(r, [{'id': 1, 'role': 'user', 'text': r['message']},
                         {'id': 2, 'role': 'assistant', 'text': '收到 ' + r['marker']}], False)
        self.assertEqual(r['state'], 'ACKNOWLEDGED')

    def test_wrong_user_message_cannot_ack(self):
        self.send(); r = self.receipt()
        chat.observe(r, [{'id': 1, 'role': 'user', 'text': 'other ' + r['marker']},
                         {'id': 2, 'role': 'assistant', 'text': r['marker']}], True)
        self.assertIsNone(r['assistant_ack'])
        self.assertTrue(r['history_window_limited'])

    def test_same_direction_reply_rejected(self):
        self.send()
        with self.assertRaises(chat.BridgeError):
            self.send('--id', 'two', '--in-reply-to', 'one')
        self.assertEqual(Fake.sends, 1)

    def test_reverse_reply(self):
        self.send()
        self.send('--id', 'two', '--from', 'dsh', '--in-reply-to', 'one')
        self.assertEqual(Fake.sends, 2)
        r = json.loads((self.state/'messages'/'two.json').read_text())
        self.assertEqual(r['target_side'], 'codex')

    def test_no_path_traversal(self):
        with self.assertRaises(chat.BridgeError):
            self.send('--id', '../escape')
        self.assertEqual(Fake.sends, 0)

    def test_lock_excludes_other_writer(self):
        with chat.locked(self.state/'locks'/'send-test'):
            with self.assertRaises(chat.BridgeError):
                self.send()
        self.assertEqual(Fake.sends, 0)

    def test_receipt_private(self):
        self.send()
        self.assertEqual((self.state/'messages'/'one.json').stat().st_mode & 0o777, 0o600)

    def test_unknown_can_reconcile_without_resend(self):
        Fake.fail = True
        with self.assertRaises(TimeoutError):
            self.send()
        r = self.receipt()
        chat.observe(r, [{'id': 1, 'role': 'user', 'text': r['message']},
                         {'id': 2, 'role': 'assistant', 'text': r['marker']}], False)
        self.assertEqual(r['state'], 'ACKNOWLEDGED')
        self.assertEqual(Fake.sends, 1)

    def test_native_desktop_envelope(self):
        text = 'A <input> literal </input> B'
        item = {'type': 'functionCallOutput', 'namespace': 'codex_app', 'name': 'send_message_to_thread',
                'output': {'text': '<codex_delegation>\n<source_thread_id>00000000-0000-0000-0000-000000000001</source_thread_id>\n<input>' + text + '</input>\n</codex_delegation>', 'truncated': False}}
        self.assertEqual(chat.desktop_incoming(item), text)
        item['output']['truncated'] = True
        self.assertIsNone(chat.desktop_incoming(item))

    def test_arbitrary_tool_output_not_inbound(self):
        item = {'type': 'functionCallOutput', 'namespace': 'shell', 'name': 'send_message_to_thread',
                'output': {'text': '<codex_delegation><input>hi</input></codex_delegation>'}}
        self.assertIsNone(chat.desktop_incoming(item))

    def test_dsh_history_requires_sequenced_cut(self):
        c = chat.DSH.__new__(chat.DSH)
        calls = []
        def rpc(method, args):
            calls.append((method, args))
            if method == 'session/projections':
                return {'kind': 'sequenced', 'asOfSeq': 42}
            return {'records': [], 'hasMore': True}
        c.rpc = rpc
        self.assertEqual(c.messages('session-id'), ([], True))
        self.assertEqual(calls[1][1]['request']['throughSeq'], 42)

    def test_redirect_rejects_origin_or_credentials_change(self):
        req = chat.urllib.request.Request('http://127.0.0.1:3090/?launch=example')
        for url in ['https://127.0.0.1:3090/', 'http://127.0.0.1:3091/',
                    'http://example.invalid/', 'http://user:pass@127.0.0.1:3090/']:
            with self.subTest(url=url), self.assertRaises(chat.BridgeError):
                chat.NoRedirect().redirect_request(req, None, 302, 'Found', {}, url)
        redirected = chat.NoRedirect().redirect_request(
            req, None, 302, 'Found', {}, 'http://127.0.0.1:3090/home')
        self.assertEqual(redirected.full_url, 'http://127.0.0.1:3090/home')

    def test_default_state_is_external_and_overridable(self):
        with patch.dict(os.environ, {'XDG_STATE_HOME': str(self.state)}, clear=True):
            module = runpy.run_path(chat.__file__, run_name='test_import')
            self.assertEqual(module['DEFAULT_STATE'], self.state/'codex-dsh-chat')
        with patch.dict(os.environ, {'CODEX_DSH_CHAT_STATE': str(self.state/'custom')}, clear=True):
            module = runpy.run_path(chat.__file__, run_name='test_import')
            self.assertEqual(module['DEFAULT_STATE'], self.state/'custom')

    def test_dsh_timezone_configuration(self):
        c = chat.DSH.__new__(chat.DSH)
        for env, expected in [({}, 'UTC'), ({'DSH_CHAT_TIMEZONE': 'Asia/Singapore'}, 'Asia/Singapore')]:
            with patch.dict(os.environ, env, clear=True), patch.object(c, 'rpc', return_value={'accepted': True}) as rpc:
                c.send('session-id', 'hello', 'request-id')
                self.assertEqual(rpc.call_args.args[1]['request']['clientTimeZone'], expected)


if __name__ == '__main__':
    unittest.main()
