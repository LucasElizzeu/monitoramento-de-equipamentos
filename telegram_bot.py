"""Telegram Bot API over verified HTTPS; never expose token-bearing URLs."""
import json
import re
import ssl
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE = 256 * 1024
TOKEN_PATTERN = r'[0-9]{5,20}:[A-Za-z0-9_-]{20,150}'
CHAT_PATTERN = r'-?[1-9][0-9]{0,19}'


class SendError(Exception):
    def __init__(self, message, retryable=False, retry_after=60):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = max(30, min(3600, retry_after))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def text_limit(text, units=4000):
    # Telegram measures message/entity offsets in UTF-16 code units.
    return text.encode('utf-16-le')[:units * 2].decode('utf-16-le', errors='ignore')


def summary(events):
    parts = ['VELOSONET · MONITORAMENTO']
    for event in events:
        kind = {'critical': 'QUEDA', 'success': 'RECUPERAÇÃO', 'warning': 'COLETA'}[event['level']]
        stamp = datetime.fromisoformat(event['event_at']).astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
        name = ' '.join(event['device_name'].split())
        message = ' '.join(event['message'].split())[:650]
        parts.append(f"{kind}\n{name} ({event['host']})\n{message}\n{stamp}")
    return text_limit('\n\n'.join(parts))


def api_error(status, payload):
    parameters = payload.get('parameters', {}) if isinstance(payload, dict) else {}
    if not isinstance(parameters, dict):
        parameters = {}
    if status == 429:
        delay = parameters.get('retry_after', 60)
        return SendError('Limite de envio do Telegram atingido. Nova tentativa em breve.', True,
                         delay if type(delay) is int else 60)
    if status >= 500:
        return SendError('O Telegram está temporariamente indisponível.', True)
    if status in (401, 404):
        return SendError('Token do bot recusado. Confira o token fornecido pelo BotFather.')
    if status == 403:
        return SendError('O bot foi bloqueado ou não tem permissão para enviar nesta conversa.')
    if status == 409:
        return SendError('O bot já usa outro coletor ou webhook. Use um bot dedicado ao monitoramento.')
    if parameters.get('migrate_to_chat_id'):
        return SendError('O grupo mudou de ID. Busque as conversas novamente e salve o novo Chat ID.')
    return SendError('Conversa não encontrada ou pedido recusado. Envie /start ao bot e confira o Chat ID.')


def request(token, method, payload):
    if not re.fullmatch(TOKEN_PATTERN, token) or method not in ('sendMessage', 'getUpdates'):
        raise SendError('Token inválido. Copie o token do bot fornecido pelo BotFather.')
    # Telegram requires the token in the path. All errors below are sanitized,
    # and redirects are refused so this URL cannot be forwarded to another host.
    req = Request(f'https://api.telegram.org/bot{token}/{method}', method='POST',
                  data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with build_opener(NoRedirect()).open(req, timeout=10) as response:
            content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise SendError('A resposta do Telegram excedeu o tamanho esperado.', True)
        result = json.loads(content)
        if not isinstance(result, dict):
            raise SendError('O Telegram não confirmou a solicitação.', True)
        if result.get('ok') is not True:
            status = result.get('error_code', 400)
            raise api_error(status if type(status) is int else 400, result)
        return result.get('result')
    except HTTPError as error:
        try:
            payload = json.loads(error.read(MAX_RESPONSE))
        except (ValueError, OSError):
            payload = {}
        finally:
            error.close()
        raise api_error(error.code, payload) from None
    except URLError as error:
        if isinstance(error.reason, ssl.SSLCertVerificationError):
            raise SendError('Certificado HTTPS não validado. Confira a confiança TLS do servidor.') from None
        raise SendError('Sem conexão com o Telegram. O evento permanece na fila para nova tentativa.', True) from None
    except (TimeoutError, OSError, ValueError):
        raise SendError('A solicitação ao Telegram não foi confirmada. Uma nova tentativa poderá ser feita.', True) from None


def send(config, token, text):
    chat_id = config.get('chat_id', '')
    if not re.fullmatch(CHAT_PATTERN, chat_id):
        raise SendError('Informe o Chat ID numérico da conversa antes de enviar.')
    result = request(token, 'sendMessage', dict(chat_id=chat_id, text=text_limit(text),
                                               link_preview_options={'is_disabled': True}))
    if (not isinstance(result, dict) or type(result.get('message_id')) is not int or result['message_id'] <= 0
            or not isinstance(result.get('chat'), dict) or str(result['chat'].get('id')) != chat_id):
        raise SendError('O Telegram não confirmou a mensagem para o destino configurado.', True)
    return str(result['message_id'])


def chats(token):
    # No offset: do not acknowledge/delete updates, or change webhook settings.
    updates = request(token, 'getUpdates', dict(limit=20, timeout=0))
    if not isinstance(updates, list):
        raise SendError('O Telegram não retornou uma lista de conversas válida.')
    found = {}
    for update in updates:
        if not isinstance(update, dict):
            continue
        for key in ('message', 'edited_message', 'channel_post', 'my_chat_member'):
            item = update.get(key)
            chat = item.get('chat') if isinstance(item, dict) else None
            if (not isinstance(chat, dict) or type(chat.get('id')) is not int
                    or not re.fullmatch(CHAT_PATTERN, str(chat['id']))
                    or chat.get('type') not in ('private', 'group', 'supergroup', 'channel')):
                continue
            name = chat.get('title') or ' '.join(str(chat.get(k, '')) for k in ('first_name', 'last_name')).strip()
            found[str(chat['id'])] = dict(id=str(chat['id']), title=str(name or chat.get('username') or chat['id'])[:120],
                                          type=chat['type'])
    return list(found.values())
