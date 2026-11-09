"""Bounded, read-only VRP queries over one interactive SSH terminal."""
import re
import socket
import time


class ReadTimeout(TimeoutError):
    def __init__(self, output):
        super().__init__('O terminal Huawei não devolveu o prompt no tempo esperado.')
        self.partial_output = output


def clean_terminal(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return text.replace('\r', '').replace('\x08', '').replace('\x00', '')


class VRPReader:
    def __init__(self, client):
        self.channel = client.invoke_shell(term='vt100', width=200, height=1000)
        self.prompt = None
        self._receive(15)

    def _receive(self, timeout):
        end = time.monotonic() + timeout
        text, paged_until = '', 0
        try:
            while time.monotonic() < end:
                self.channel.settimeout(min(1, max(.01, end - time.monotonic())))
                try:
                    chunk = self.channel.recv(8192)
                except socket.timeout:
                    continue
                if not chunk:
                    raise EOFError('O Huawei encerrou o terminal antes de concluir a consulta.')
                text += chunk.decode('utf-8', 'replace')
                if len(text) > 131072:
                    raise ValueError('A resposta do terminal Huawei excedeu o limite da consulta.')
                output = clean_terminal(text)
                # VRP can page even a single interface; space advances only its output.
                for marker in re.finditer(r'-{2,}\s*More\s*-{2,}', output, re.I):
                    if marker.end() > paged_until:
                        self.channel.sendall(' ')
                        paged_until = marker.end()
                if self.prompt is None:
                    match = re.search(r'(?:^|\n)(<[^<>\n]+>|\[[^\[\]\n]+\])\s*$', output)
                    if match:
                        self.prompt = match[1]
                        return output[:match.start()]
                else:
                    match = re.search(r'(?:^|\n)' + re.escape(self.prompt) + r'\s*$', output)
                    if match:
                        output = output[:match.start()]
                        return re.sub(r'-{2,}\s*More\s*-{2,}', '', output, flags=re.I)
            raise ReadTimeout(clean_terminal(text))
        except Exception:
            # A partial response must never be reused by a subsequent command.
            self.channel.close()
            raise

    def read(self, command):
        if not re.fullmatch(r'(?:display|show) [a-zA-Z0-9 /_.:-]{1,150}', command):
            raise ValueError('Use somente comandos de consulta display/show no terminal Huawei.')
        self.channel.sendall(command + '\n')
        output = self._receive(20)
        lines = output.splitlines()
        if lines and lines[0].strip() in (command, self.prompt + command):
            lines.pop(0)
        return '\n'.join(lines).strip()
