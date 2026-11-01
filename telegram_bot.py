"""Telegram Bot API over verified HTTPS; never expose token-bearing URLs."""
import json
import alert_labels
import re
import ssl
from datetime import datetime, timezone, timedelta
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


def event_time(value):
    if not value:
        return 'não registrado'
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    # Manaus is UTC-4 with no DST. A fixed offset also works on Windows without
    # installing the optional tzdata package. Storage remains UTC.
    return stamp.astimezone(timezone(timedelta(hours=-4))).strftime('%d/%m/%Y às %H:%M:%S')


def event_duration(started, ended):
    if not started:
        return 'não registrado'
    try:
        start, end = datetime.fromisoformat(started), datetime.fromisoformat(ended)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        elapsed = (end - start).total_seconds()
        if elapsed < 0:
            return 'não disponível'
        seconds = int(elapsed)
    except (TypeError, ValueError, OverflowError):
        return 'não disponível'
    parts = []
    for unit, divisor in (('d', 86400), ('h', 3600), ('min', 60), ('s', 1)):
        value, seconds = divmod(seconds, divisor)
        if value:
            parts.append(f'{value} {unit}')
    return ' '.join(parts) or '0 s'


def summary(events):
    parts = []
    for event in events:
        resolved = event['level'] == 'success'
        started = event.get('incident_started_at') or (None if resolved else event['event_at'])
        fault = event.get('incident_cause') or alert_labels.cause(event['message'], event['level'], event.get('topic'))
        name = text_limit(' '.join(event['device_name'].split()), 160)
        fault = text_limit(' '.join(fault.split()), 600)
        lines = [f'{"🟢" if resolved else "🔴"} {name}', f'Causa: {fault}']
        if resolved:
            lines.extend([f'Resolvido: {event_time(event["event_at"])}',
                          f'Tempo fora: {event_duration(started, event["event_at"])}'])
        else:
            lines.append(f'Iniciado: {event_time(started)}')
        parts.append('\n'.join(lines))
    return text_limit('\n\n'.join(parts))


def api_error(status, payload):
    parameters = payload.get('parameters', {}) if isinstance(payload, dict) else {}
    description = payload.get('description', '') if isinstance(payload, dict) else ''
    description = description[:4096].lower() if isinstance(description, str) else ''
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
    if "can't initiate conversation" in description:
        return SendError('O destinatário ainda não iniciou conversa com este bot. Abra o bot correspondente ao token, envie /start e busque as conversas novamente.')
    if "can't send messages to bots" in description:
        return SendError('O destino é outro bot. Escolha sua conversa pessoal ou um grupo em Buscar conversas.')
    if 'blocked by the user' in description:
        return SendError('O destinatário bloqueou este bot. Desbloqueie o bot no Telegram e envie /start novamente.')
    if 'kicked from' in description or 'not a member' in description:
        return SendError('Este bot não faz parte do grupo ou canal. Adicione-o ao destino e busque as conversas novamente.')
    if 'not enough rights' in description or 'have no rights' in description or 'chat_write_forbidden' in description:
        return SendError('O bot não tem permissão para enviar mensagens no grupo ou canal. Confira as permissões do bot no destino.')
    if status == 403:
        return SendError('O bot foi bloqueado ou não tem permissão para enviar nesta conversa.')
    if status == 409:
        return SendError('O bot já usa outro coletor ou webhook. Use um bot dedicado ao monitoramento.')
    if parameters.get('migrate_to_chat_id'):
        return SendError('O grupo mudou de ID. Busque as conversas novamente e salve o novo Chat ID.')
    if 'chat not found' in description:
        return SendError('O Telegram não encontrou este Chat ID para o bot configurado. Abra o bot correspondente ao token, envie /start, selecione o destino em Buscar conversas e salve antes de testar.')
    if 'chat_id is empty' in description:
        return SendError('O destino está vazio. Selecione uma conversa e salve o Chat ID antes de testar.')
    if 'message text is empty' in description or 'message is too long' in description:
        return SendError('O Telegram recusou o tamanho do texto da mensagem. Atualize o programa e teste novamente.')
    if 300 <= status < 400:
        return SendError('A conexão foi redirecionada. O envio foi interrompido para proteger o token. Confira a conexão HTTPS com api.telegram.org.')
    return SendError(f'O Telegram recusou a solicitação (HTTP {status}). O motivo não foi reconhecido; confira a conexão e a configuração do bot.')


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
    if chat_id == token.partition(':')[0]:
        raise SendError('Este Chat ID é o ID do próprio bot. Use o ID da sua conversa ou grupo: envie /start ao bot, clique em Buscar conversas, escolha o destino e salve.')
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
