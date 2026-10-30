"""Bounded SSH ping collection for the Datacom output supplied by the user."""
import ipaddress
import math
import re
import time


class RemotePingError(Exception):
    def __init__(self, message, output=''):
        super().__init__(message)
        self.output = output[:16000]


def parse_remote_ping(host, output):
    address = ipaddress.ip_address(host)
    summary = re.search(r'(\d+) packets transmitted,\s*(\d+) (?:packets )?received', output)
    header = re.search(r'^PING\s+\S+\s+\(([^)]+)\)', output, re.M)
    try:
        correct_target = header and ipaddress.ip_address(header[1]) == address
    except ValueError:
        correct_target = False
    if not summary or not correct_target:
        raise RemotePingError('Resultado de ping não reconhecido. Confira a saída do Datacom.', output)
    transmitted, received = map(int, summary.groups())
    if not 1 <= transmitted <= 20 or not 0 <= received <= transmitted:
        raise RemotePingError('Quantidade de pacotes inesperada no ping do Datacom.', output)
    replies = {}
    for line in output.splitlines():
        match = re.search(r'^\d+ bytes from (\S+):\s+icmp_seq=(\d+)\s+.*?time([=<])([\d.,]+)\s*ms', line)
        if not match:
            continue
        try:
            sender = ipaddress.ip_address(match[1])
        except ValueError:
            continue
        seq = int(match[2])
        if sender == address and 1 <= seq <= transmitted and seq not in replies:
            replies[seq] = 0.0 if match[3] == '<' else float(match[4].replace(',', '.'))
    if len(replies) != received:
        raise RemotePingError('As respostas não correspondem ao resumo do ping. Confira a saída do Datacom.', output)
    latency = None
    if received:
        stats = re.search(r'(?:rtt|round-trip)[^\n=]*=\s*[\d.,]+/([\d.,]+)/', output)
        latency = float(stats[1].replace(',', '.')) if stats else sum(replies.values()) / received
        if not math.isfinite(latency) or latency < 0:
            raise RemotePingError('Latência não reconhecida no ping do Datacom.', output)
    return dict(transmitted=transmitted, received=received, latency=latency,
                probes=[seq in replies for seq in range(1, transmitted + 1)])


def read_remote_ping(client, host, cancelled=lambda: False, deadline_seconds=45):
    # The supplied DmOS command finishes after five packets. The absolute
    # deadline and output limit also close the channel on other firmware.
    command = f'ping {ipaddress.ip_address(host)}'
    _, stdout, _ = client.exec_command(command, timeout=6)
    channel = stdout.channel
    output, errors = bytearray(), bytearray()
    deadline = time.monotonic() + deadline_seconds
    try:
        while True:
            if cancelled():
                raise RemotePingError('Consulta interrompida.', output.decode('utf-8', 'replace'))
            if time.monotonic() >= deadline:
                raise RemotePingError('O ping do Datacom não terminou em até 45 segundos.', output.decode('utf-8', 'replace'))
            if channel.recv_ready():
                output.extend(channel.recv(4096))
            if channel.recv_stderr_ready():
                errors.extend(channel.recv_stderr(1024))
            if len(output) > 16000 or len(errors) > 4000:
                raise RemotePingError('Saída de ping acima do limite da consulta.', output.decode('utf-8', 'replace'))
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(.03)
        text = output.decode('utf-8', 'replace')
        if channel.recv_exit_status() not in (0, 1) or errors.strip():
            raise RemotePingError('O Datacom recusou a execução do ping.', text + '\n' + errors.decode('utf-8', 'replace'))
        return text
    finally:
        channel.close()
