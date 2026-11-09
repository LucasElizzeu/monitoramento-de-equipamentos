import socket
import unittest
from unittest.mock import Mock, patch

from huawei_ssh import VRPReader, ReadTimeout

PROMPT = b'<MANAUS-HUAWEI-S6730>'


class FakeChannel:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
        self.closed = False

    def settimeout(self, seconds):
        self.timeout = seconds

    def recv(self, count):
        if not self.chunks:
            raise socket.timeout()
        item = self.chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def sendall(self, value):
        self.sent.append(value)

    def close(self):
        self.closed = True


class HuaweiTerminalTests(unittest.TestCase):
    def reader(self, chunks):
        channel = FakeChannel([b'Welcome\r\n' + PROMPT, *chunks])
        client = Mock()
        client.invoke_shell.return_value = channel
        return VRPReader(client), channel, client

    def test_waits_for_split_prompt_and_reuses_session_for_multiple_commands(self):
        cmd = 'display interface XGigabitEthernet 0/0/11'
        reader, channel, client = self.reader([
            cmd.encode() + b'\r\nXGigabitEthernet0/0/11 current state : UP\r\n',
            socket.timeout(), b'<MANAUS-HUAWEI-', b'S6730>',
            b'display interface XGigabitEthernet 0/0/12\r\nXGigabitEthernet0/0/12 current state : DOWN\r\n' + PROMPT])
        self.assertEqual(reader.read(cmd), 'XGigabitEthernet0/0/11 current state : UP')
        self.assertIn('DOWN', reader.read('display interface XGigabitEthernet 0/0/12'))
        client.invoke_shell.assert_called_once()
        client.exec_command.assert_not_called()
        self.assertFalse(channel.closed)

    def test_pagination_can_span_chunks_and_advances_each_marker_once(self):
        reader, channel, _ = self.reader([
            b'XGigabitEthernet0/0/11 current state : UP\r\n---- Mo',
            b're ----', b'\x1b[2K\r\nLast 300 seconds input rate 123 bits/sec\r\n',
            b'---- More ----', b'\r\nRX Power(dBM) : -23.10\r\n' + PROMPT])
        output = reader.read('display interface XGigabitEthernet 0/0/11')
        self.assertEqual(channel.sent.count(' '), 2)
        self.assertNotIn('More', output)
        self.assertIn('123 bits/sec', output)
        self.assertIn('-23.10', output)

    def test_timeout_preserves_diagnostic_only_and_closes_desynchronized_channel(self):
        reader, channel, _ = self.reader([b'partial output without prompt'])
        with patch('huawei_ssh.time.monotonic', side_effect=range(1000)):
            with self.assertRaises(ReadTimeout) as error:
                reader.read('display interface XGigabitEthernet 0/0/11')
        self.assertIn('partial output', error.exception.partial_output)
        self.assertTrue(channel.closed)

    def test_closed_connection_or_excessive_output_is_not_success(self):
        for chunks, error in [([b''], EOFError), ([b'x' * 131073], ValueError)]:
            with self.subTest(error=error):
                reader, channel, _ = self.reader(chunks)
                with self.assertRaises(error):
                    reader.read('display interface XGigabitEthernet 0/0/11')
                self.assertTrue(channel.closed)

    def test_no_configuration_commands_or_separators_can_be_sent(self):
        reader, channel, _ = self.reader([])
        for command in ['system-view', 'shutdown', 'display interface; reboot', 'display interface\nreboot']:
            with self.assertRaises(ValueError):
                reader.read(command)
        self.assertEqual(channel.sent, [])
