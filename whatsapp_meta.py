"""WhatsApp Cloud API template sender. No redirects or credentials in URLs/logs."""
import json
import re
import ssl
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE = 65536


class SendError(Exception):
    def __init__(self, message, retryable=False, retry_after=60):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = max(30, min(3600, retry_after))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def summary(events):
    parts = []
    for event in events:
        kind = {'critical': 'QUEDA', 'success': 'RECUPERAÇÃO', 'warning': 'COLETA'}[event['level']]
        stamp = datetime.fromisoformat(event['event_at']).astimezone(timezone.utc).strftime('%d/%m %H:%M UTC')
        # Template body parameters must not contain newlines, tabs or long runs of spaces.
        part = f"{kind}: {event['device_name']} ({event['host']}) · {event['message'][:120]} · {stamp}"
        parts.append(' '.join(part.split())[:290])
    return ' | '.join(parts)[:900]


def api_error(status, payload):
    error = payload.get('error', {}) if isinstance(payload, dict) else {}
    code = error.get('code') if isinstance(error, dict) else None
    if status == 429 or code in (4, 80007, 130429, 131056):
        return SendError('Limite de envio da Meta atingido. Nova tentativa em breve.', True, 120)
    if status >= 500 or code in (1, 2, 131000):
        return SendError('A Meta está temporariamente indisponível.', True, 60)
    if status in (401, 403) or code in (10, 190, 200):
        return SendError('A Meta recusou o acesso. Confira o token e a permissão whatsapp_business_messaging.')
    if code in (132001, 132015, 132016):
        return SendError('Modelo não disponível. Confira o nome, idioma e aprovação do modelo na Meta.')
    if code in (132000, 132012):
        return SendError('O modelo deve ter exatamente uma variável de texto no corpo, sem outras variáveis.')
    if code in (131026, 131030):
        return SendError('Destino não autorizado ou indisponível. Confira o número com DDI e os destinatários de teste da Meta.')
    return SendError('A Meta recusou o envio. Confira o ID do número, destino e modelo aprovado.')


def send(config, token, text):
    # Validate again at the network boundary: the host is never user configurable.
    if (not re.fullmatch(r'v\d{1,3}\.0', config['api_version'])
            or not re.fullmatch(r'\d{1,30}', config['phone_number_id'])
            or not re.fullmatch(r'[1-9]\d{7,14}', config['recipient'])
            or not re.fullmatch(r'[a-z0-9_]{1,512}', config['template_name'])
            or not re.fullmatch(r'[a-z]{2}(?:_[A-Z]{2})?', config['language'])
            or not re.fullmatch(r'[A-Za-z0-9_.|:-]{20,4096}', token)):
        raise SendError('Configuração inválida. Salve novamente as credenciais e os dados do WhatsApp.')
    text = ' '.join(text.split())[:900]
    payload = dict(messaging_product='whatsapp', to=config['recipient'], type='template',
                   template=dict(name=config['template_name'], language=dict(code=config['language']),
                                 components=[dict(type='body', parameters=[dict(type='text', text=text)])]))
    request = Request(f"https://graph.facebook.com/{config['api_version']}/{config['phone_number_id']}/messages",
                      data=json.dumps(payload).encode(), method='POST',
                      headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise SendError('A resposta da Meta excedeu o tamanho esperado.', True)
        result = json.loads(content)
        messages = result.get('messages') if isinstance(result, dict) else None
        if (not isinstance(messages, list) or not messages or not isinstance(messages[0], dict)
                or not isinstance(messages[0].get('id'), str) or not messages[0]['id']):
            raise SendError('A Meta não confirmou a aceitação da mensagem.', True)
        return messages[0]['id'][:512]
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
        raise SendError('Sem conexão com a Meta. O evento permanece na fila para nova tentativa.', True) from None
    except (TimeoutError, OSError, ValueError):
        raise SendError('O envio não foi confirmado. Uma nova tentativa poderá ser feita.', True) from None
