# VELOSONET MONITORAMENTO

Primeira versão de um painel local para monitorar ping e interfaces de equipamentos Datacom por SSH. Interface em português, responsiva, com identidade VELOSONET e tema azul-marinho. Textos claros e indicadores em verde, vermelho e âmbar destacam os estados dos equipamentos. Não requer etapa de compilação ou serviços de fontes externos. Python 3.12+, FastAPI, SQLite e JavaScript.

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

O painel principal usa o **visual Compacto**, com cartões menores, menos espaçamento e letras proporcionais. A largura dos cartões é padronizada entre os Datacoms na mesma tela: equipamentos com poucas portas mantêm o mesmo tamanho compacto dos que têm muitas portas, sem esticar os cartões para ocupar a linha inteira. No celular, a grade usa uma coluna. Sinais, consumo e pings permanecem juntos; os detalhes continuam disponíveis ao expandir cada saída.

Para comparar propostas de cartões e letras menores, use **Comparar opções de visual** no rodapé ou abra `/static/design-options.html`. Os modelos **1 · Equilibrado**, **2 · Compacto** e **3 · Em lista** usam a interface real com dados de demonstração, sem alterar os equipamentos cadastrados ou salvar uma preferência de visual. O modelo em lista usa linhas no desktop e cartões em telas menores. Escolher um modelo nesta página muda apenas a prévia; o painel principal permanece no modelo Compacto.

Imagens das propostas: [1 · Equilibrado](docs/visual-equilibrado.png), [2 · Compacto](docs/visual-compacto.png) e [3 · Em lista](docs/visual-lista.png).

- **BBU's:** equipamentos cadastrados como ping, com disponibilidade, latência e perdas consecutivas.
- **Datacoms:** equipamentos SSH, com disponibilidade, portas, descrições e sinais RX/TX.
- **Visão geral:** resumo conjunto da rede.
- **Eventos:** histórico conjunto de quedas, recuperações e erros de coleta.

Clique no **IP de uma BBU** para abrir seu site em uma nova aba, no endereço `http://IP/`. O atalho aparece na aba **BBU's** e na **Visão geral**, inclusive no celular; o monitoramento continua aberto na aba original. O endereço precisa disponibilizar uma interface web acessível pela sua rede.

Os equipamentos existentes aparecem na aba correspondente ao tipo já cadastrado, sem migração do banco ou novo cadastro. Cada aba possui sua lista e seus contadores; o botão de adicionar já seleciona o tipo correspondente. A regra de alerta permanece na 21ª perda consecutiva.

Clique no ícone **!** de qualquer cartão de resumo para abrir a lista correspondente: equipamentos monitorados, online, sem ping, portas inativas ou BBU's instáveis. A lista respeita a aba atual e o total do cartão, independentemente do filtro de busca da tabela. Em **Portas inativas**, aparecem o nome personalizado da porta (ou a descrição original, se não houver nome), Datacom, IP, tipo de interface, número da porta e posição no circuito. Gigabit e Ten com o mesmo número permanecem separados. Portas de Datacoms com erro na consulta SSH não entram no total nem na lista como leituras atuais.

As listas permanecem estáveis para leitura enquanto o monitoramento continua; use **Atualizar lista** para trazer o estado mais recente. O horário da lista aparece no cabeçalho. **Ver equipamento** abre os detalhes do equipamento escolhido. Cartões com total zero também podem ser abertos e mostram uma mensagem de lista vazia. O botão de fechar ou a tecla Esc retornam ao painel.

## Ordem do circuito e nomes personalizados

Na edição de cada Datacom (lápis da linha), preencha **Posição no circuito** com 1, 2, 3 ou posições intermediárias como **2.1** e **2.2**, para organizar trechos com duas rotas. O campo aceita ponto ou vírgula (`2.1` ou `2,1`), de 1 a 10000. A sequência será **2 → 2.1 → 2.2 → 3**. A aba Datacoms e os blocos de portas seguem essa ordem numérica. Os que estiverem sem posição aparecem no final; posições iguais mantêm a ordem de cadastro. Apague o número para voltar à ordenação sem posição. As posições são salvas no banco e permanecem ao reiniciar.

Para substituir no painel descrições como `SWITCH_DM4380-CAA...`, clique no **lápis ao lado do nome da porta**, digite o nome desejado e salve. Exemplos: `Entrada do circuito`, `Saída para Anori` ou `Link principal`. A personalização vale para o painel e os novos alertas. A descrição original do Datacom aparece na janela de edição e na saída do equipamento.

Os eventos de queda e recuperação, tanto na **Visão geral** quanto na aba **Eventos**, incluem o nome personalizado da porta. Sem nome personalizado, usam a descrição informada pelo Datacom. Exemplo: `Porta Ten Gigabit Ethernet 1/1/11 (Saída para Anori) caiu (link down).` O Datacom continua identificado logo abaixo. Novos eventos guardam esse nome junto da mensagem, inclusive se o equipamento for removido depois. Eventos antigos que só tinham o número recebem o nome na exibição quando ainda for possível identificar a interface; o registro original no banco é preservado. Números antigos sem tipo que correspondam a Giga e Ten simultaneamente permanecem sem nome para não associar a porta errada.

Os nomes são vinculados ao Datacom, ao tipo de interface e ao número da porta; Gigabit `1/1/1` e Ten `1/1/1` podem ter nomes diferentes. Novas consultas SSH preservam os nomes personalizados. Deixe o campo vazio para voltar à descrição original. O nome do Datacom inteiro continua editável no cadastro do equipamento.

## Circuitos: ping a partir do Datacom

Configure os destinos dentro do cadastro do Datacom que deve executar os pings:

1. Na aba **Datacoms**, clique no **lápis** do Datacom de origem.
2. Abra **Ping de circuitos (opcional)** e clique em **Adicionar IP**. Informe o destino, por exemplo **10.91.0.2**, e um nome opcional. Se o nome ficar vazio, será usado `Circuito IP`.
3. Escolha o intervalo entre testes: **30 segundos por padrão**, de 10 a 300 segundos.
   Em **Porta do cartão (opcional)**, selecione onde o ping deve aparecer junto do sinal óptico e do consumo. Por exemplo, associe o circuito MAMIRAUÁ à porta **1/1/5 · Giga · MAMIRAUA**.
4. Repita para os demais IPs e clique em **Salvar alterações**. A consulta começa automaticamente; **Testar agora**, no cartão do circuito, solicita uma nova leitura.

**Os pings aparecem na mesma grade das portas e sinais.** Quando uma porta é escolhida, o resumo do ping fica dentro do cartão dela, junto dos sinais e do consumo. Pings sem vínculo aparecem em cartões pequenos separados nessa mesma grade. A escolha organiza a exibição; o comando `ping IP` continua usando a rota configurada no Datacom. O vínculo identifica a origem, o tipo de interface e o número da porta, mantendo Gigabit e Ten com o mesmo número separados. Se a porta sair das leituras atuais ou a consulta de sinais falhar, o ping permanece visível em um cartão separado, preservando o vínculo para quando a porta voltar.

Os Datacoms sem IPs de circuito exibem somente suas portas, sem uma caixa vazia de circuitos. A lista pode ser configurada tanto no cadastro inicial quanto na edição. Os IPs existentes são preservados e aparecem nesse formulário; o vínculo com uma porta é opcional. O atalho **Configurar IPs**, nos Datacoms que já têm circuitos, abre a configuração correspondente.

Os IPs são salvos junto com o Datacom: **Cancelar** não altera a lista. **Remover IP** retira uma linha do formulário; a remoção só é aplicada ao salvar. Para desativar todos os circuitos desse Datacom, remova as linhas e salve. A mudança afeta apenas essa origem e preserva os eventos anteriores. Nomes e intervalos podem ser editados sem perder a última leitura; trocar o destino limpa os resultados antigos. Listas inválidas não salvam alterações parciais. Se outra janela alterar os IPs durante a edição, o formulário solicita reabertura para evitar sobrescrever a configuração mais recente.

O servidor conecta por SSH ao Datacom escolhido, verifica a impressão digital cadastrada e executa **`ping IP`**, usando as mesmas credenciais do equipamento. O ping de disponibilidade do próprio Datacom, na lista de equipamentos, continua saindo do computador do programa. Os cartões de circuito testam o destino a partir da rede do Datacom. O mesmo IP pode ser monitorado por Datacoms diferentes; dentro de um Datacom, o IP não pode ser duplicado.

O resumo compacto de cada ping mostra nome, IP, estado, latência média, perdas e horário. Abra **Detalhes do ping** para ver a quantidade de respostas do último teste, intervalo, botões de testar/editar/remover e **Copiar saída** com o resultado original. A atualização visual pausa durante a leitura. A mesma organização aparece em **Ver detalhes** do Datacom.

A leitura reconhece a saída fornecida para `ping 10.91.0.2`: cinco respostas, **0% de perda** e média **3,204 ms**. No firmware informado, o comando termina após cinco pacotes. As perdas são contadas **por pacote**, usando `icmp_seq`, e uma resposta zera a sequência de perdas. **Mais de 20 perdas consecutivas** geram um evento com nome do circuito, IP e Datacom de origem. Por exemplo, quatro testes sem nenhuma resposta somam 20 perdas; ao receber o resultado do quinto, o contador chega a 25 e o evento registra a passagem pela 21ª perda. A recuperação também gera evento. Falha de autenticação, chave inválida, consulta interrompida ou saída não reconhecida aparecem como **Erro de coleta**, sem aumentar perdas.

O próximo teste aguarda o anterior terminar. Os pings remotos têm uma fila de execução separada dos pings locais das BBU's. Cada execução do comando é limitada a 45 segundos e 16 KB de saída. Esta versão aceita a sintaxe simples confirmada, sem VRF ou IP de origem personalizados. Há limite de 20 circuitos por Datacom e 100 circuitos no painel. Apenas IPs são aceitos como destino; o comando é construído pelo programa, sem comandos livres.

Os circuitos ficam no mesmo SQLite, na pasta `.data`. A tabela é criada automaticamente na atualização, preservando equipamentos, senhas e nomes existentes. Editar nome ou intervalo mantém a última leitura. Trocar o destino ou os dados de acesso da origem limpa as leituras antigas; resultados de consultas anteriores à edição são descartados. Remover um Datacom remove os circuitos associados e preserva os eventos. Para converter um Datacom em BBU, primeiro remova seus circuitos.

**Validação:** parser e fluxo completo foram testados com a saída enviada e um cliente SSH simulado. Não houve acesso à rede privada do usuário para validar o comando em equipamento físico.

## Organização da interface

O tema azul-marinho e a marca **VELOSONET MONITORAMENTO** foram mantidos. As informações de equipamentos, eventos, sinais e consumo usam letras maiores. Em telas menores, a lista de equipamentos vira cartões com status, IP, latência, perdas e última checagem visíveis juntos, além dos botões **Editar**, **Detalhes** e **Remover**. Nos Datacoms, pings e portas compartilham a mesma grade; pings vinculados aparecem dentro do cartão da porta. O cabeçalho resume portas ativas e inativas. Os nomes das portas ganham destaque, com sinal óptico e consumo separados.

## Ping

- Cadastre nome, IP IPv4/IPv6 e intervalo de 1 a 300 segundos (1 segundo por padrão). Equipamentos existentes mantêm seu intervalo até serem editados.
- Cada tentativa envia um pacote ICMP. O tempo máximo de resposta é independente do intervalo: **4 segundos por padrão**, editável de 1 a 30 segundos. A versão anterior reduzia a espera para 0,8 segundo quando o intervalo era 1 segundo, podendo perder respostas lentas. O intervalo é contado entre os inícios das tentativas; se a anterior ainda estiver aguardando resposta, a próxima espera sua conclusão. Assim, no intervalo de 1 segundo e timeout de 4 segundos, um alvo silencioso pode ser consultado aproximadamente a cada 4 segundos. Não são enviadas sondas sobrepostas. Sob carga, os horários dependem da disponibilidade dos coletores.
- De 1 a 20 perdas consecutivas: **Instável**.
- Na **21ª perda consecutiva**: **Sem ping**, com um evento de queda.
- Resposta recebida: contador zerado. Se estava sem ping, registra recuperação.
- Erro local de socket/permissão: **Erro de coleta**, sem incrementar perdas.
- Amostras e eventos são persistidos no SQLite. Retenção: 720 amostras por equipamento e 1.000 eventos; o painel mostra os 60 eventos recentes. A janela do gráfico depende da quantidade de equipamentos e do intervalo de coleta, não é uma janela de disponibilidade contratual.

### Permissão e acesso à rede

No **Windows**, o coletor usa o `PING.EXE` da pasta System32, com um pacote de 32 bytes, a mesma ferramenta disponível no CMD. A execução dispensa sockets raw do Python e não abre novas janelas. O programa interpreta respostas do alvo em português/inglês, incluindo latência abaixo de 1ms (representada como 0ms na resolução inteira do Windows). Mensagens de host inacessível não são consideradas sucesso mesmo se o comando retornar código zero. Falhas locais de execução e saídas não reconhecidas são erros de coleta e não aumentam a contagem de perdas. A seleção do backend ocorre automaticamente no sistema em que o servidor está rodando.

Em **Linux/Unix**, o coletor usa sockets ICMP sem privilégios via `icmplib`, também com payload de 32 bytes. Linux precisa permitir o grupo do processo em `net.ipv4.ping_group_range`. Um administrador pode incluir o GID do usuário nessa faixa; preserve grupos já autorizados na máquina. Não execute a aplicação inteira como root para resolver isso.

Para um contêiner Linux, o administrador pode definir esse sysctl no contêiner, por exemplo `--sysctl net.ipv4.ping_group_range="0 2147483647"` para autorizar os grupos no namespace do contêiner. Essa configuração não é aplicada automaticamente pelo programa.

**Limitação observada neste ambiente na nuvem:** o parâmetro está em `1 0`, bloqueando ICMP sem privilégios; o processo também não tem permissão para criar sockets raw nem instalar pacotes de sistema como administrador. Por isso o ping real não foi validado aqui. O programa detecta essa condição e mostra erro de coleta. É necessário executar em um servidor com ICMP permitido para monitoramento real.

O servidor também precisa alcançar os IPs da sua rede. Um proxy HTTP não transporta ICMP e não substitui a conectividade SSH. Para equipamentos privados, use um computador na rede de gerenciamento ou uma rota/VPN administrada e autorizada. Este projeto não cria VPNs nem libera firewalls.

### Comparar com o ping manual

No computador que executa o programa, compare o alvo usando `ping -n 4 IP` no CMD do Windows. Testar de outro computador não comprova que o servidor tem a mesma rota/VPN/interface de saída. No painel, abra **Ver detalhes** (seta da linha): **Última tentativa de ping** mostra a ferramenta usada, o timeout e o resultado, inclusive mensagens do `ping.exe`. Envie esse diagnóstico se o comportamento continuar diferente. Não há acesso aos IPs privados do usuário a partir desta tarefa; as saídas do Windows foram testadas com casos simulados, e não houve validação em uma máquina Windows real nesta etapa.

## Editar equipamentos

Clique no **lápis** da linha do equipamento, nas abas BBU's, Datacoms ou Visão geral. É possível alterar nome, IP, intervalo, tempo máximo de resposta do ping, tipo, portas e configurações SSH sem recriar o cadastro.

Ao editar um Datacom, deixe a senha vazia para manter a atual; preencha apenas para substituí-la. A senha nunca é enviada de volta ao navegador. Nome/intervalo preservam as amostras. Se trocar IP ou tipo, as amostras e estados do alvo anterior são limpos para evitar misturar medições, mas o ID e os eventos históricos são preservados. Consultas iniciadas antes da edição não sobrescrevem a configuração atualizada.

## Ler e copiar a saída

Ao abrir **Ver saída do equipamento** ou selecionar texto, a atualização **visual** é pausada para manter o conteúdo estável. O monitoramento e a busca de novas leituras continuam em segundo plano. Feche a saída ou clique em **Retomar atualização** para exibir os novos dados.

Use **Copiar saída** para copiar os textos dos comandos. Se o navegador bloquear a área de transferência, selecione o texto e use Ctrl+C; a seleção será preservada durante a leitura. A interface busca novas leituras a cada segundo; a consulta SSH permanece a cada 30 segundos.

## Datacom

Cadastre tipo **Datacom via SSH**, IP, usuário, senha e impressão digital SHA256 da chave do servidor. Obtenha a impressão digital por um canal confiável com o administrador/console do equipamento. Chaves divergentes são rejeitadas antes de enviar a senha. Prefira usuário de consulta com permissões somente de leitura.

Comandos padrão informados para este projeto:

```text
show interface link
show interface transceivers
show interface utilization
```

O comando óptico padrão foi corrigido para `transceivers`. Ao iniciar, cadastros Datacom que ainda usam exatamente o antigo padrão `show interface tranceivers` são corrigidos automaticamente, preservando credenciais e histórico. Comandos personalizados são mantidos. Se o firmware rejeitar uma consulta com `syntax error: unknown argument` ou outra indicação de comando inválido, o painel informa qual comando foi rejeitado, mesmo quando o SSH retorna código de saída zero. Ajuste a sintaxe do modelo em **Editar → Comandos do equipamento**.

- Consultas SSH a cada 30 segundos.
- Em **Tipo de interface**, escolha **Gigabit Ethernet (Giga)**, **Ten Gigabit Ethernet (Ten)** ou **Hundred Gigabit Ethernet**, conforme as portas que deseja acompanhar. A seleção vale para estado, descrição e sinais ópticos. Para um Datacom já cadastrado, use o lápis, selecione Ten e salve; a senha pode ficar vazia para manter a atual.
- Para tipos simultâneos, escolha **Gigabit + Ten (selecionar portas)**. Surgem duas listas independentes: **Portas Ten Gigabit** e **Portas Gigabit**. Exemplo: Ten `10, 11, 12` e Giga `19, 20` consulta somente essas cinco interfaces; Giga `1/1/10` fica excluída. Números simples usam `1/1/N`; para outro slot/chassi, informe o caminho completo, como `2/1/10`.
- No modo misto, preencha ao menos uma lista. A API armazena cada seleção com tipo explícito, como `ten:1/1/10` e `giga:1/1/19`; mesmo número pode aparecer nas duas listas sem compartilhar estado, sinal, nome ou alerta. O formulário restaura as duas listas ao editar. Use as consultas gerais `show interface link` e `show interface transceivers` nesse modo, sem o marcador `{port}`.
- **Automático** mantém a compatibilidade com listagens em que cada número identifica um único tipo. Se `1/1/1` aparecer em seções Gigabit, Ten ou Hundred, o coletor solicita uma seleção explícita em vez de usar o estado ou o sinal de outra interface. Se o tipo já estiver selecionado e o formato ainda não puder ser identificado, o aviso indica uma falha de interpretação, sem pedir a mesma seleção novamente. Nenhum tipo é escolhido pelo estado Up/Down ou pela velocidade negociada.
- Os cartões identificam o tipo físico, e o histórico de transições considera tipo + número da porta. Alterar o tipo invalida as leituras anteriores e inicia nova consulta, preservando credenciais e dados de ping.
- Deixe a lista de portas vazia para detectar as interfaces **do tipo selecionado** na listagem `show interface link` (até 128 portas por equipamento). Ou selecione portas separadas por vírgula: `1/1/21, 1/1/22`.
- O parser mantém as seções Gigabit, Ten e Hundred separadas, inclusive variações como `TenGigabitEthernet Interfaces:`, `Ten-GigabitEthernet Interfaces:` e `10GE Interfaces:`. Também reconhece os prefixos compactos e com hífen nas linhas ópticas, preserva quebras de linha CR/LF e reúne linhas RX/TX da mesma interface. Estados Up/Down conflitantes continuam sendo sinalizados, sem escolher um arbitrariamente. Ele foi adaptado às linhas fornecidas:

```text
1/1/21   Up    false     1G     full    -    -    -    TELEBRAS-ANORI
1/1/22   Up    false     1G     full    -    -    -    TELEBRAS-LTE-ANORI

gigabit-ethernet 1/1/21 | 45.73 C | 3.37 V | 19.77 mA | -6.51 dBm | -12.96 dBm
gigabit-ethernet 1/1/22 | 54.14 C | 3.3 V  | 19.77 mA | -6.39 dBm | -9.53 dBm
```

A leitura óptica usa rótulos RX/TX ou o cabeçalho da tabela quando disponíveis. Sem cabeçalho, as duas últimas colunas dBm do formato fornecido são interpretadas como TX e RX, respectivamente. Temperatura/tensão/corrente podem estar ausentes, e são aceitos graus °C, vírgula decimal e linhas de diagnóstico quebradas. Os valores aparecem nos cartões com até duas casas decimais. Sinal ausente ou não reconhecido fica como `—`, nunca zero; uma medição ausente não apaga a outra. O formato real de cada firmware deve ser confirmado pela saída original.

O painel mostra descrição, link, RX/TX, horário da leitura e a saída original. Formatos desconhecidos ficam como **Não identificado**. Se a consulta SSH falhar, leituras anteriores não são exibidas como atuais. Uma porta inicialmente Down gera um evento; novas consultas Down não duplicam o alerta; a volta para Up registra recuperação.

Cada cartão mostra **Consumo na porta**, com apenas a banda de entrada **RX em L1**. A consulta `show interface utilization` é feita uma vez por equipamento, junto das consultas SSH a cada 30 segundos. Os valores são exibidos em bps, Kbps, Mbps ou Gbps, conforme a escala. O parser reconhece o formato fornecido:

```text
                             L1 RX      L1 TX      L2 RX      L2 TX
INTERFACE NAME               BANDWIDTH  BANDWIDTH  BANDWIDTH  BANDWIDTH
-------------------------------------------------------------------------
ten-gigabit-ethernet-1/1/11  2.5Gbps    162.1Mbps  2.4Gbps    151.4Mbps
```

Para essa linha, **Consumo na porta** exibe **2,5 Gbps**, correspondente ao RX em L1. TX e L2 permanecem apenas na saída original para diagnóstico. São as taxas reportadas pelo equipamento na consulta; o painel não calcula médias adicionais nem mantém histórico de banda nesta versão. Tipo e número da porta são respeitados, inclusive no modo Gigabit + Ten. Valores ausentes ou formatos desconhecidos aparecem como `—`; zero só aparece quando informado pelo equipamento. A saída de utilização também está em **Ver saída do equipamento → Copiar saída**.

O comando de banda é adicionado automaticamente aos cadastros existentes, preservando senhas, posições e nomes. Se ele for recusado ou sua consulta falhar, o cartão informa o problema e mantém o monitoramento de link e sinais. Em **Editar → Comandos do equipamento → Consultar utilização de banda**, ajuste a consulta geral ou deixe o campo vazio para desativar apenas a banda. Essa consulta não aceita `{port}`.

Os comandos podem ser ajustados por modelo. Aceitam apenas `show`/`display`, sem operadores de shell. Opcionalmente, use `{port}` para consultar cada porta separadamente (nesse caso, informe uma lista de portas). A conexão usa requisições SSH exec; firmwares que só aceitam shell interativo/paginação poderão precisar de um adaptador posterior.

**Não houve conexão com equipamento físico nesta etapa.** O parser e as transições foram testados com os exemplos fornecidos e um cliente SSH simulado. A validação com o modelo/firmware e a rede reais ainda está pendente.

### Diagnóstico de falhas SSH

Se a leitura falhar, abra **Ver diagnóstico da consulta SSH**, abaixo do aviso. Ele mostra o tipo salvo, a etapa em que houve falha, os comandos e as saídas originais disponíveis, mesmo quando os cartões não puderam ser montados. Use **Copiar diagnóstico** para enviar essas informações ao suporte; a senha não é incluída. A atualização visual fica pausada durante a leitura, da mesma forma que na saída dos cartões. Ao editar a conexão, o diagnóstico anterior é limpo; a próxima consulta gera um resultado novo.

## Dados e segurança

- Credenciais criptografadas com Fernet; a API nunca retorna a senha.
- Arquivos locais em `.data/`, ignorados pelo Git. O banco e a chave têm permissões restritas; guarde ambos ao fazer backup e proteja o volume. A chave local permite descriptografar o banco, portanto criptografia não substitui controle de acesso ao servidor.
- Diretório alternativo: variável `MONITOR_DATA_DIR`.
- Esta versão é de uso **local**, sem login/múltiplos usuários, notificações por e-mail/WhatsApp ou gestão de permissões. Os alertas aparecem no painel e no histórico.
- Mantenha o bind em `127.0.0.1`. Antes de expor para uma equipe, acrescente autenticação, HTTPS e regras de acesso. Não publique a porta diretamente na internet.
- Limite desta versão: 100 equipamentos. Ainda não foi feito teste de carga com esse volume.
- Circuitos remotos: até 100 no painel, com máximo de 20 por Datacom.

## Validação

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip check
node --check static/app.js
```

Os testes cobrem o limiar de 20/21 perdas, recuperação, perdas intercaladas, erro de ICMP, parser das linhas Datacom, detecção automática de portas, transições Up/Down, isolamento de interfaces, validação de entradas, criptografia, rejeição de chave SSH e remoção de amostras.

API de saúde: `GET /api/health`. API e documentação OpenAPI disponíveis no próprio servidor em `/docs`.

O teste de navegador desta implementação verificou demonstração, busca, detalhes, navegação de portas, formulário SSH, cadastro/exclusão real via API e responsividade a 390px. O ICMP real foi bloqueado pelas permissões do ambiente e não é reportado como aprovado.
