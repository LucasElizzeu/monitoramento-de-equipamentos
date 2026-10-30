"""ALFOplus2 web login and read-only IF-MIB counters."""
import ipaddress
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT_OID = '1.3.6.1.2.1.2.2.1'
LEAVES = ['1', '10', '11', '12', '13', '14', '16', '17', '18', '19']
MAX_RESPONSE = 256 * 1024
MAX_SAMPLE_SECONDS = 10


class SiaeError(Exception):
    pass


class SiaeSessionError(SiaeError):
    """A session was rejected; automatic mode may renew it once."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SiaeError('O rádio redirecionou a consulta. Confira HTTP/HTTPS e a porta web.')


def counter(value):
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int or not 0 <= value < 2**32:
        raise SiaeError('Contador de bytes inválido na resposta do rádio.')
    return value


def parse_table(payload, indices):
    if not isinstance(payload, dict) or type(payload.get('Err')) is not int:
        raise SiaeError('Formato da resposta de interfaces não reconhecido.')
    if payload['Err'] != 0:
        raise SiaeSessionError('O rádio recusou a consulta. Confira a sessão Id e a permissão de leitura.')
    if type(payload.get('More')) is not int or payload['More'] != 0:
        raise SiaeError('A tabela recebida está incompleta; a banda não pode ser calculada.')
    rows = payload.get('val')
    if not isinstance(rows, list) or len(rows) > 2048:
        raise SiaeError('Formato da tabela de interfaces não reconhecido.')
    result = {}
    seen = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(LEAVES) + 1:
            raise SiaeError('Formato da linha de interfaces não reconhecido.')
        index = counter(row[1])
        if index < 1 or str(index) != str(row[0]) or index in seen:
            raise SiaeError('Índice de interface inválido ou duplicado na resposta.')
        seen.add(index)
        if index in indices:
            result[index] = {'rx_octets': counter(row[2]), 'tx_octets': counter(row[7])}
    if set(result) != set(indices):
        raise SiaeError('Interface configurada não encontrada na tabela do rádio.')
    return result


def post_json(host, scheme, port, endpoint, payload):
    host = str(ipaddress.ip_address(host))
    if scheme not in ('http', 'https') or not 1 <= port <= 65535:
        raise SiaeError('Endereço web do rádio inválido.')
    address = f'[{host}]' if ':' in host else host
    suffix = '' if port == (443 if scheme == 'https' else 80) else f':{port}'
    origin = f'{scheme}://{address}{suffix}'
    request = Request(origin + endpoint, method='POST',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'X-Requested-With': 'XMLHttpRequest', 'Origin': origin})
    try:
        with build_opener(NoRedirect()).open(request, timeout=5) as response:
            content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise SiaeError('Resposta do rádio excedeu o limite da consulta.')
        try:
            result = json.loads(content)
        except (ValueError, UnicodeError):
            if endpoint == '/Snmp.GetTable':
                raise SiaeSessionError('Resposta não reconhecida. Entre no rádio e renove a sessão Id.') from None
            raise SiaeError('Resposta do login não reconhecida. Use a sessão Id manual e confira o formato do login.') from None
        return result
    except HTTPError as exc:
        if exc.code in (401, 403):
            if endpoint == '/Log.Login':
                raise SiaeError('Login recusado pelo rádio. Confira usuário, senha e permissão de acesso.') from None
            raise SiaeSessionError('Sessão Id recusada ou expirada. Entre no rádio e atualize a sessão.') from None
        raise SiaeError(f'Falha HTTP {exc.code} ao consultar o rádio.') from None
    except (URLError, TimeoutError, OSError):
        raise SiaeError('Não foi possível acessar o rádio. Confira IP, HTTP/HTTPS, porta e rede.') from None


def login(host, scheme, port, username, password):
    payload = post_json(host, scheme, port, '/Log.Login', {'Usr': username, 'Pwd': password})
    if not isinstance(payload, dict):
        raise SiaeError('Resposta do login não reconhecida: esperado um objeto com a sessão Id. Use a sessão manual.')
    if 'Err' in payload and (type(payload['Err']) is not int or payload['Err'] != 0):
        raise SiaeError('Login recusado pelo rádio. Confira usuário, senha e permissão de acesso.')
    session = payload.get('Id', payload.get('id'))
    if not isinstance(session, str) or not re.fullmatch(r'[!-~]{1,512}', session):
        raise SiaeError('Resposta do login sem uma sessão Id válida. Use a sessão manual e confira o formato da resposta de Log.Login.')
    return session


def read_counters(host, scheme, port, session, indices):
    return parse_table(post_json(host, scheme, port, '/Snmp.GetTable',
                                {'Id': session, 'rad': ROOT_OID, 'lea': LEAVES}), indices)


def calculate_rates(previous, current, seconds):
    if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_SAMPLE_SECONDS:
        return None, 'Intervalo entre leituras fora do limite. Aguardando nova amostra.'
    if set(previous) != set(current):
        return None, 'Interfaces alteradas. Aguardando nova amostra.'
    rates = {}
    for index, values in current.items():
        old = previous[index]
        # The observed counters are 32-bit. A decrease could be a reset OR a wrap;
        # without a device discontinuity marker, never guess a spike or a total.
        if values['rx_octets'] < old['rx_octets']:
            return None, 'Contador reiniciado ou completou uma volta. Aguardando nova amostra.'
        rates[index] = {'rx_bps': (values['rx_octets'] - old['rx_octets']) * 8 / seconds,
                        'tx_bps': ((values['tx_octets'] - old['tx_octets']) * 8 / seconds
                                   if values['tx_octets'] >= old['tx_octets'] else None)}
    return rates, None
