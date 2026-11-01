"""Human-readable notification text, keeping original panel history intact."""
import re


def cause(message, level, topic=None):
    """Describe the fault, including when formatting its recovery event."""
    ping = re.fullmatch(r'Sem ping: (\d+) perdas consecutivas\.', message)
    if ping:
        return f'Sem resposta ao ping ({ping[1]} perdas consecutivas).'
    if topic == 'ping' or message.startswith('Ping restabelecido.'):
        return 'Sem resposta ao ping.'
    if topic == 'port' or message.startswith('Porta '):
        return re.sub(r'(?:caiu \(link down\)|restabelecida)\.$', 'sem conexão.', message)
    if topic == 'circuit' or message.startswith('Circuito '):
        return message.replace('voltou a responder pelo Datacom.', 'sem resposta ao ping pelo Datacom.')
    if message.startswith('Leitura de banda SIAE restabelecida.'):
        return 'Falha na consulta de banda do rádio.'
    return message

def title(message, level, topic=None):
    if message.startswith('Falha ao ler banda SIAE:'):
        return 'Não foi possível consultar a banda do rádio'
    if message.startswith('Leitura de banda SIAE restabelecida'):
        return 'Consulta de banda do rádio normalizada'
    if topic == 'port' or message.startswith('Porta '):
        return 'Porta voltou a ter conexão' if level == 'success' else 'Porta perdeu a conexão'
    if topic == 'circuit' or message.startswith('Circuito '):
        if level == 'warning':
            return 'Não foi possível verificar o circuito'
        return 'Circuito voltou a responder' if level == 'success' else 'Circuito sem resposta'
    if topic == 'ping' or message.startswith(('Sem ping:', 'Ping restabelecido.')):
        return 'Equipamento voltou a responder' if level == 'success' else 'Equipamento sem resposta ao ping'
    if level == 'warning':
        return 'Não foi possível consultar o equipamento'
    return {'critical': 'Problema detectado', 'success': 'Monitoramento normalizado'}.get(level, 'Evento de monitoramento')
