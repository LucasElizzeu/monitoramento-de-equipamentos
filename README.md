# Nexo · Monitoramento de equipamentos

Primeira versão de um painel local para monitorar ping e interfaces de equipamentos Datacom por SSH. Interface em português, responsiva e sem etapa de compilação ou serviços de fontes externos. Python 3.12+, FastAPI, SQLite e JavaScript.

## Executar

No diretório do projeto:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

Abra a interface na porta 8000 do computador que executa o programa. O botão **Ver demonstração** apresenta dados simulados, separados dos equipamentos reais. Nenhum IP de exemplo é consultado. Ao adicionar um equipamento, o painel passa para a sua rede real.

Use somente **um processo/worker** do servidor, para evitar consultas e eventos duplicados. A máquina precisa permanecer ligada para monitorar. Os horários são armazenados em UTC e exibidos no fuso do navegador.

## Abas do painel

- **BBU's:** equipamentos cadastrados como ping, com disponibilidade, latência e perdas consecutivas.
- **Datacoms:** equipamentos SSH, com disponibilidade, portas, descrições e sinais RX/TX.
- **Visão geral:** resumo conjunto da rede.
- **Eventos:** histórico conjunto de quedas, recuperações e erros de coleta.

Os equipamentos existentes aparecem na aba correspondente ao tipo já cadastrado, sem migração do banco ou novo cadastro. Cada aba possui sua lista e seus contadores; o botão de adicionar já seleciona o tipo correspondente. A regra de alerta permanece na 21ª perda consecutiva.

## Ping

- Cadastre nome, IP IPv4/IPv6 e intervalo (5 segundos por padrão).
- Cada tentativa envia um pacote ICMP, com timeout de 1,5 segundo.
- De 1 a 20 perdas consecutivas: **Instável**.
- Na **21ª perda consecutiva**: **Sem ping**, com um evento de queda.
- Resposta recebida: contador zerado. Se estava sem ping, registra recuperação.
- Erro local de socket/permissão: **Erro de coleta**, sem incrementar perdas.
- Amostras e eventos são persistidos no SQLite. Retenção: 720 amostras por equipamento e 1.000 eventos; o painel mostra os 60 eventos recentes. A janela do gráfico depende da quantidade de equipamentos e do intervalo de coleta, não é uma janela de disponibilidade contratual.

### Permissão e acesso à rede

O coletor usa sockets ICMP sem privilégios via `icmplib`. Linux precisa permitir o grupo do processo em `net.ipv4.ping_group_range`. Um administrador pode incluir o GID do usuário nessa faixa; preserve grupos já autorizados na máquina. Não execute a aplicação inteira como root para resolver isso.

Para um contêiner Linux, o administrador pode definir esse sysctl no contêiner, por exemplo `--sysctl net.ipv4.ping_group_range="0 2147483647"` para autorizar os grupos no namespace do contêiner. Essa configuração não é aplicada automaticamente pelo programa.

**Limitação observada neste ambiente na nuvem:** o parâmetro está em `1 0`, bloqueando ICMP sem privilégios; o processo também não tem permissão para criar sockets raw nem instalar pacotes de sistema como administrador. Por isso o ping real não foi validado aqui. O programa detecta essa condição e mostra erro de coleta. É necessário executar em um servidor com ICMP permitido para monitoramento real.

O servidor também precisa alcançar os IPs da sua rede. Um proxy HTTP não transporta ICMP e não substitui a conectividade SSH. Para equipamentos privados, use um computador na rede de gerenciamento ou uma rota/VPN administrada e autorizada. Este projeto não cria VPNs nem libera firewalls.

## Datacom

Cadastre tipo **Datacom via SSH**, IP, usuário, senha e impressão digital SHA256 da chave do servidor. Obtenha a impressão digital por um canal confiável com o administrador/console do equipamento. Chaves divergentes são rejeitadas antes de enviar a senha. Prefira usuário de consulta com permissões somente de leitura.

Comandos padrão informados para este projeto:

```text
show interface link
show interface tranceivers
```

A grafia `tranceivers` foi preservada conforme informada. Se o seu firmware usar `transceivers`, ajuste no cadastro, em **Comandos do equipamento**.

- Consultas SSH a cada 30 segundos.
- Deixe a lista de portas vazia para detectar as interfaces da listagem `show interface link` (até 128 portas por equipamento). Ou selecione portas separadas por vírgula: `1/1/21, 1/1/22`.
- O parser foi adaptado às linhas fornecidas:

```text
1/1/21   Up    false     1G     full    -    -    -    TELEBRAS-ANORI
1/1/22   Up    false     1G     full    -    -    -    TELEBRAS-LTE-ANORI

gigabit-ethernet 1/1/21 | 45.73 C | 3.37 V | 19.77 mA | -6.51 dBm | -12.96 dBm
gigabit-ethernet 1/1/22 | 54.14 C | 3.3 V  | 19.77 mA | -6.39 dBm | -9.53 dBm
```

A ordem óptica adotada é **temperatura, tensão, corrente, TX, RX**, usual nesse formato. O cabeçalho completo do equipamento ainda precisa confirmar TX/RX. Os dois valores são exibidos individualmente; sinal ausente fica como `—`, nunca zero. Temperatura/tensão/corrente não são confundidas com dBm.

O painel mostra descrição, link, RX/TX, horário da leitura e a saída original. Formatos desconhecidos ficam como **Não identificado**. Se a consulta SSH falhar, leituras anteriores não são exibidas como atuais. Uma porta inicialmente Down gera um evento; novas consultas Down não duplicam o alerta; a volta para Up registra recuperação.

Os comandos podem ser ajustados por modelo. Aceitam apenas `show`/`display`, sem operadores de shell. Opcionalmente, use `{port}` para consultar cada porta separadamente (nesse caso, informe uma lista de portas). A conexão usa requisições SSH exec; firmwares que só aceitam shell interativo/paginação poderão precisar de um adaptador posterior.

**Não houve conexão com equipamento físico nesta etapa.** O parser e as transições foram testados com os exemplos fornecidos e um cliente SSH simulado. A validação com o modelo/firmware e a rede reais ainda está pendente.

## Dados e segurança

- Credenciais criptografadas com Fernet; a API nunca retorna a senha.
- Arquivos locais em `.data/`, ignorados pelo Git. O banco e a chave têm permissões restritas; guarde ambos ao fazer backup e proteja o volume. A chave local permite descriptografar o banco, portanto criptografia não substitui controle de acesso ao servidor.
- Diretório alternativo: variável `MONITOR_DATA_DIR`.
- Esta versão é de uso **local**, sem login/múltiplos usuários, notificações por e-mail/WhatsApp ou gestão de permissões. Os alertas aparecem no painel e no histórico.
- Mantenha o bind em `127.0.0.1`. Antes de expor para uma equipe, acrescente autenticação, HTTPS e regras de acesso. Não publique a porta diretamente na internet.
- Limite desta versão: 100 equipamentos. Ainda não foi feito teste de carga com esse volume.

## Validação

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip check
node --check static/app.js
```

Os testes cobrem o limiar de 20/21 perdas, recuperação, perdas intercaladas, erro de ICMP, parser das linhas Datacom, detecção automática de portas, transições Up/Down, isolamento de interfaces, validação de entradas, criptografia, rejeição de chave SSH e remoção de amostras.

API de saúde: `GET /api/health`. API e documentação OpenAPI disponíveis no próprio servidor em `/docs`.

O teste de navegador desta implementação verificou demonstração, busca, detalhes, navegação de portas, formulário SSH, cadastro/exclusão real via API e responsividade a 390px. O ICMP real foi bloqueado pelas permissões do ambiente e não é reportado como aprovado.
