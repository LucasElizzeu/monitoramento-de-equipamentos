"""Plain-language event titles shared by the dashboard and Telegram."""

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
