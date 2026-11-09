# VELOSONET MONITORAMENTO

A interface usa AlwaysUp como marca principal e a logo Velosonet NOC em tamanho menor, sem texto adicional. No celular e no tablet, a marca menor aparece na barra superior.

Painel local para monitorar ping e interfaces de equipamentos Datacom por SSH. Interface em português, responsiva, com a logo VELOSONET NOC e tema branco compacto. Textos escuros e indicadores em verde, vermelho e âmbar destacam os estados dos equipamentos. Não requer etapa de compilação ou serviços de fontes externos. Python 3.12+, FastAPI, SQLite e JavaScript.

## Executar

No diretório do projeto:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

Abra a interface na porta 8000 do computador que executa o programa. O painel abre diretamente os equipamentos cadastrados. O modo demonstração e os elementos decorativos da lateral foram removidos.

Use somente **um processo/worker** do servidor, para evitar consultas e eventos duplicados. A máquina precisa permanecer ligada para monitorar. Os horários são armazenados em UTC e exibidos no fuso do navegador.

## Abas do painel

### Backbone Veloso NOC — fibra e rádio

A aba **Backbone Veloso NOC** mostra o backbone informado, com 15 equipamentos e 28 fibras independentes. Coari fica à esquerda e Manaus à direita; as rotas via Nazaré e via KM60/Membeca/Caapiranga se encontram em Anamã. TELEBRÁS, INFOVIA, SMART e a fibra local entre os Datacoms de Tefé aparecem separadamente. O mapa também inclui as duas redes de rádio de Coari a Tefé.

As duas fibras TELEBRÁS entre Anori e Coari usam trajetos retangulares com cantos arredondados, em faixas separadas. A INFOVIA liga o Huawei de Manaus (`10.200.1.1`, Ten 0/0/23) ao Escritório de Tefé (`10.200.24.1`, Ten 1/1/4) e segue o mesmo estilo pela parte superior do desenho, preservando as cores de status e os detalhes de cada interface. Os equipamentos têm mais espaço entre si, e as leituras acompanham a direção de cada fibra, junto à linha correspondente. A tela inicia ajustada à área disponível e mostra apenas nomes e tráfego. O seletor **Exibir** permite mostrar todos os detalhes (IPs e sinal óptico) ou somente os pontos; a preferência fica salva no navegador. Os dados completos continuam disponíveis ao consultar cada fibra. A legenda e a ajuda ficam abaixo do mapa.

Cada equipamento é associado ao cadastro pelo IP. Clique no ponto para abrir seus detalhes ou iniciar o cadastro: não são criados equipamentos nem credenciais automaticamente. O Huawei abre a configuração de consulta SSH VRP, com as portas Ten identificadas individualmente.

As linhas exibem consumo RX e sinal RX de ambas as pontas, na ordem origem/destino. Verde exige leitura atual e porta ativa nas duas pontas; vermelho indica porta caída; amarelo indica erro de coleta; cinza tracejado indica manutenção, porta pendente, equipamento ausente ou falta de leitura atual. Leituras com mais de 90 segundos não são usadas como atuais. O estado informado durante o levantamento não substitui a coleta real.

Passe o mouse na fibra para consultar as portas: a janela fecha ao sair tanto da fibra quanto da própria janela, mesmo depois de clicar. Você pode mover o mouse para **Editar portas / manutenção** antes que ela feche. No celular, toque para abrir e toque fora para fechar; pelo teclado, use Tab/Enter e Escape. Alterações ficam no SQLite e acompanham os backups. A porta do Huawei que alimenta o Datacom 2 de Manaus começa pendente. A fibra Manaus XGE0/0/11 ↔ Limão Ten 1/1/2 começa em manutenção, que pode ser desmarcada após o reparo. Use identificadores completos, como `ten-gigabit-ethernet:1/1/3` ou `gigabit-ethernet:1/1/21`, para separar Ten e Giga.

Em telas menores, o desenho permite rolagem horizontal; **Ajustar à tela** alterna a visão completa. O desenho inicial está em `static/backbone.json`; as edições de porta não alteram esse arquivo.

[Ver captura do mapa com leituras simuladas de validação](docs/mapa-backbone.png).

O painel principal usa o **visual Compacto**, com cartões menores, menos espaçamento e letras proporcionais. A largura dos cartões é padronizada entre os Datacoms na mesma tela: equipamentos com poucas portas mantêm o mesmo tamanho compacto dos que têm muitas portas, sem esticar os cartões para ocupar a linha inteira. No celular, a grade usa uma coluna. Sinais, consumo e pings permanecem juntos; os detalhes continuam disponíveis ao expandir cada saída.

- **BBU's:** equipamentos cadastrados como ping, com disponibilidade, latência e perdas consecutivas.
- **Datacoms:** equipamentos SSH, com disponibilidade, portas, descrições e sinais RX/TX.
- **Rádios SIAE:** cadastro separado, ping local e leitura de banda por sessão web do ALFOplus2.
- **Visão geral:** resumo conjunto da rede.
- **Eventos:** histórico conjunto de quedas, recuperações e erros de coleta.

Clique no **IP de uma BBU** para abrir seu site em uma nova aba, no endereço `http://IP/`. O atalho aparece na aba **BBU's** e na **Visão geral**, inclusive no celular; o monitoramento continua aberto na aba original. O endereço precisa disponibilizar uma interface web acessível pela sua rede.

## Consumo das portas — últimas 24 horas

Na aba **Datacoms**, abra **Consumo 24h** no cabeçalho da área de portas. Cada cartão com leitura de banda também tem **Ver gráfico 24h**, que abre o painel já filtrado pela interface escolhida.

O painel mostra **RX**, a mesma medida de **Consumo na porta**, com **última leitura**, **média das leituras válidas** e **pico no período**. Os filtros permitem escolher Datacom, porta e buscar pelo nome personalizado ou número. Gigabit e Ten com o mesmo número têm históricos separados. Por padrão, entram as portas que tiveram tráfego positivo nas últimas 24 horas, inclusive se agora estiverem zeradas. Marque **Incluir portas com apenas leituras zeradas** para ver também portas sempre ociosas.

Passe o mouse, toque no gráfico ou use as setas do teclado para consultar horário e valor. Os gráficos usam o fuso do navegador, mantêm a janela completa de 24 horas e são atualizados a cada 30 segundos enquanto o painel está aberto. **Atualizar** recarrega os dados imediatamente. São exibidos até seis gráficos por página para manter o painel leve.

**O histórico começa após instalar esta atualização**, a partir das novas consultas de utilização do Datacom (a cada 30 segundos). Não há preenchimento retroativo. A primeira amostra aparece como um ponto; o traçado cresce conforme novas leituras chegam. Falhas de SSH, consumo indisponível, portas fora da seleção e intervalos sem medições formam **lacunas**, sem substituir dados ausentes por zero. A média usa somente amostras válidas; zero medido é um valor válido.

As leituras ficam no SQLite existente (`.data/monitor.db`), continuam disponíveis depois de reiniciar o programa e são removidas periodicamente quando saem da janela de 24 horas. O programa precisa permanecer ligado para coletar o período inteiro. Renomear uma porta atualiza o título do gráfico e preserva as amostras. Trocar o IP ou tipo do equipamento reinicia seu histórico, evitando misturar fontes diferentes; remover o equipamento também remove suas séries.

Os dados de teste simulados são utilizados somente nas validações automatizadas; o painel operacional não oferece modo demonstração.

## Rádios SIAE — ping e consumo de banda

Na aba **Rádios SIAE**, cadastre o nome e o IP do ALFOplus2. O ping sai do computador que executa o programa, com a mesma regra de alerta na 21ª perda consecutiva. Cadastro, edição, remoção, histórico e listas de status estão disponíveis. O IP abre a interface web do rádio em outra aba.

Para configurar a banda, clique em **Configurar banda** no cartão (ou edite o rádio) e abra **Consumo de banda · ALFOplus2**:

1. Marque **Ativar leitura automática de banda**.
2. Informe **HTTP/HTTPS** e a **porta web** usados para acessar esse rádio. Na captura fornecida, o acesso era HTTP, porta 80. O destino sempre usa o IP cadastrado.
3. Em **Acesso ao rádio**, escolha **Login automático com usuário e senha** e informe as credenciais diretamente no formulário. O programa faz `POST /Log.Login` com os campos `Usr` e `Pwd`, usa a sessão `Id` retornada e confirma o acesso consultando os contadores. Os cadastros antigos continuam no modo **Sessão manual (Id)**; para migrar, edite o rádio e escolha o login automático. Não envie credenciais pelo chat.
4. Escolha **Uma interface TRX** e o índice **3** para a interface **Gi0/3 — TRX** mostrada na captura. Essa opção mede uma interface, sem inventar leituras separadas para A/B. Verifique na configuração do seu rádio se esse contador representa o enlace completo.
5. Se o equipamento apresentar **duas interfaces distintas** para os TRX, escolha **TRX A + B** e informe os dois índices correspondentes. O mesmo índice não pode ser usado duas vezes. Nunca some duas cópias do contador agregado.
6. Mantenha o intervalo de **2 segundos** (aceita 2 a 5) e salve. A primeira consulta prepara a medição; o consumo aparece após a próxima leitura válida.

O coletor usa o POST de leitura **`/Snmp.GetTable`**, com o formato observado: `rad: 1.3.6.1.2.1.2.2.1`, folhas `1,10,11,12,13,14,16,17,18,19` e a sessão `Id`. O campo **Received Octets** é convertido em taxa: **(bytes atuais − bytes anteriores) × 8 ÷ segundos entre as leituras**. O cartão mostra **RX**; no modo com dois índices, soma RX A + RX B. Os campos **ETH Capacity** e a soma de RX + TX não são usados como consumo.

A senha e a sessão são armazenadas criptografadas no mesmo banco e com a mesma chave de credenciais do programa. As respostas da API nunca retornam seus valores. Deixe a senha vazia na edição para manter a senha salva. Ao trocar IP, protocolo, porta ou usuário, informe a senha novamente. Credenciais novas descartam a sessão anterior. No login automático, uma sessão recusada permite uma única tentativa de renovação por coleta; a leitura seguinte prepara uma nova medição para evitar diferenças falsas. Após falha de banda/login, o coletor aguarda **30 segundos** antes de tentar novamente, mantendo o ping independente. Desmarcar a coleta interrompe as consultas de banda.

A resposta real de `Log.Login` ainda precisa ser validada no equipamento físico: o coletor aceita um objeto JSON com uma sessão textual `Id` (ou `id`) e rejeita erros explícitos, ausência de sessão, redirecionamentos e formatos desconhecidos, sem registrar credenciais ou o corpo da resposta. Se o firmware responder de outro modo, o cartão mostrará o diagnóstico e você poderá usar **Sessão manual (Id)**: no navegador já conectado ao rádio, abra **F12 → Network → Snmp.GetTable → Payload**, copie somente o valor de `Id` e cole no formulário. A sessão manual não é renovada automaticamente; deixe vazio para manter a sessão salva ou cole uma nova quando expirar. Ao trocar IP, protocolo ou porta, informe uma nova sessão.

Falhas de sessão/conexão, interfaces ausentes ou tabelas incompletas deixam o consumo **indisponível**, sem contar como perda de ping. Em caso de erro, abra **Ver diagnóstico da banda → Copiar diagnóstico** no cartão. O diagnóstico informa a etapa (credencial salva, login ou interfaces), a classe do erro e a conexão configurada, sem incluir senha, sessão ou corpo da resposta. Enquanto a saída está aberta, a tela fica estável para leitura; as consultas continuam. Se a chave de credenciais do computador não abrir a senha ou sessão salva, informe novamente esse campo em **Editar banda**. No modo automático, uma sessão corrompida pode ser recuperada com um novo login quando a senha salva ainda está válida. A leitura e seu horário aparecem no cartão. Os contadores observados são de 32 bits: quando diminuem (reinício ou volta do contador), o programa descarta essa diferença e aguarda a próxima amostra, evitando picos falsos. Intervalos acima de 10 segundos também reiniciam a medição para reduzir ambiguidades. O coletor limita as respostas e não segue redirecionamentos com a sessão. Consultas web usam uma fila separada dos pings.

O modo demonstração usa exemplos explícitos de **120 Mbps + 80 Mbps = 200 Mbps**; esses números não são leituras reais. A validação automatizada usa respostas no formato enviado e um rádio HTTP simulado localmente; a leitura e o login no equipamento físico dependem da conexão, das credenciais e do formato de resposta do firmware na sua rede.

### Diagnosticar acesso web da banda

As requisições de login e contadores usam JSON compacto em UTF-8, com o charset declarado no Content-Type. O conteúdo das credenciais é preservado, inclusive acentos e espaços.

O botão **Consultar banda agora** solicita uma coleta pela fila web existente, sem esperar os 30 segundos após uma falha. É preciso ter a leitura habilitada; uma consulta já em andamento não é duplicada. O cálculo continua exigindo duas leituras válidas e não altera o ping.

`BadStatusLine` indica que o cliente não recebeu um status HTTP válido, antes de validar os contadores. O diagnóstico distingue uma porta que responde como SSH, uma resposta TLS recebida por HTTP, status HTTP fora do formato e conexão encerrada pelo rádio. Não é, por si só, uma confirmação de senha errada. Use o mesmo protocolo e porta do navegador; não desative a validação HTTPS. Se a página inicial retorna HTTP 200, mas o login falha, confira os metadados da requisição de login no navegador (URL, método, status e Content-Type), sem copiar senha, cookies, sessão ou o corpo da resposta.

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

A tipografia principal é **Manrope**, com pesos variáveis e fonte incluída no próprio projeto em `static/fonts/`. Cartões brancos usam cantos de 12 px e sombras suaves sobre fundo cinza muito claro. A fonte funciona sem acesso a serviços externos; sua licença SIL Open Font License acompanha o arquivo. Saídas de comandos e endereços em código preservam fonte monoespaçada.

[Ver captura real do estilo Manrope com dados simulados](docs/visual-manrope.png).

### Ajustes do menu e navegação por teclado

No computador ou tablet, o botão **☰** recolhe o menu para uma faixa de 72 px e o expande novamente. O botão **Ajustar menu** (engrenagem) permite escolher uma largura de 180 a 300 px. As preferências ficam salvas neste navegador; **Restaurar padrão** volta a 232 px.

A primeira parada do teclado é **Pular para o conteúdo principal**. Ao mudar de aba, o título da janela é atualizado e o foco vai para o título da página. Os controles têm indicação de foco visível, e os itens do menu mantêm nomes acessíveis quando recolhidos. Essas mudanças atendem a aspectos de navegação dos critérios WCAG 2.4; não representam uma auditoria completa de conformidade do site.

No mapa, arraste com o mouse ou com um dedo para mover a visualização. Use **+**, **−** e **Ajustar à tela** para zoom. Com a área do mapa focada, as setas movem a visualização e as teclas `+` e `−` ajustam o zoom; os atalhos de zoom do navegador com Ctrl/Command são preservados. O link **Pular o desenho do mapa** evita percorrer todas as fibras com Tab. Isso movimenta a visualização e não altera os pontos ou as conexões cadastradas.

Os ícones dos equipamentos seguem o mesmo estilo azul e verde: torre LTE para BBU, torre com antenas de prato para SIAE e switch para Datacom. Eles aparecem na navegação, na seleção de tipo e junto aos equipamentos. São ilustrações fixas; o estado real continua indicado pelos textos e pelas cores de status.

O tema **branco compacto** usa a logo **VELOSONET NOC**, fundo branco, textos escuros e detalhes azuis na navegação e nas ações. Em telas menores, a lista de equipamentos vira cartões com status, IP, latência, perdas e última checagem visíveis juntos, além dos botões **Editar**, **Detalhes** e **Remover**. Nos Datacoms, pings e portas compartilham a mesma grade; pings vinculados aparecem dentro do cartão da porta. O cabeçalho resume portas ativas e inativas. Os nomes das portas ganham destaque, com sinal óptico e consumo separados.

Na aba **Datacoms**, os cartões aparecem diretamente abaixo do resumo, da busca e dos filtros, sem repetir a tabela de equipamentos acima deles. Em telas grandes, há quatro cartões por linha; no celular, uma coluna. Editar, abrir detalhes, remover e configurar IPs continuam disponíveis no cabeçalho de cada Datacom. A busca e o filtro de status atuam sobre esses grupos de cartões.

O resumo **Online** informa o ping do Datacom. **Em alerta** lista Datacoms com instabilidade, erro de coleta, porta inativa ou circuito com alerta; um Datacom que responde ao ping pode ter alerta em uma porta ou circuito. Datacoms sem ping aparecem no resumo separado **Sem ping**. Isso não altera o estado coletado de cada equipamento.

O bloco de ping do circuito mostra **verde quando online**, **amarelo em instabilidade ou erro de coleta**, **vermelho quando sem ping** e **cinza enquanto aguarda leitura**. O texto do estado continua visível, sem depender apenas da cor. O estado do circuito é independente do estado da porta física; uma porta ativa pode conter um circuito sem ping. As cores não alteram os critérios do monitoramento nem o alerta na 21ª perda consecutiva.

[Ver captura do tema branco compacto com dados fictícios](docs/visual-branco-compacto.png).

[Ver captura da tela completa de Datacoms com dados fictícios](docs/painel-branco-compacto.png).

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
- Esta versão é de uso **local**, sem login/múltiplos usuários ou gestão de permissões. Os alertas aparecem no painel e no histórico; o envio por Telegram é opcional e configurado na aba Notificações.
- Mantenha o bind em `127.0.0.1`. Antes de expor para uma equipe, acrescente autenticação, HTTPS e regras de acesso. Não publique a porta diretamente na internet.
- Limite desta versão: 100 equipamentos. Ainda não foi feito teste de carga com esse volume.
- Circuitos remotos: até 100 no painel, com máximo de 20 por Datacom.

## Disponibilidade de 7 e 30 dias

A aba **Disponibilidade** mostra o percentual de tempo com resposta ao ping, tempo sem resposta, quedas confirmadas e cobertura da coleta por equipamento. Escolha **7 dias** ou **30 dias** e busque pelo nome ou IP. As barras representam cada data, da mais antiga à atual; a legenda separa resposta, perda, erro e ausência de medição. A demonstração inclui um histórico simulado separado dos dados reais.

- O período abrange 7 ou 30 **datas UTC, incluindo hoje até o momento da consulta**. As datas são identificadas como UTC no painel. Os relatórios são atualizados a cada 30 segundos e pelo botão Atualizar.
- Disponibilidade = tempo com resposta ÷ (tempo com resposta + tempo sem resposta). É uma medida do **ping**, não da banda, do SSH ou do serviço entregue ao cliente. Perdas abaixo do limiar de alerta também entram no tempo sem resposta.
- **Quedas confirmadas** conta cada entrada na 21ª perda consecutiva. Uma sequência longa gera uma queda, e uma recuperação permite contar a próxima. Não confundir essa contagem com o número de pacotes perdidos.
- Erros locais de ICMP são mostrados separadamente e ficam fora do percentual. Períodos sem coleta também ficam fora: nunca se presume que o equipamento permaneceu online durante todo o tempo em que o programa esteve desligado.
- Uma leitura vale até a próxima leitura ou seu prazo de validade: o maior entre duas vezes o intervalo e intervalo + timeout + 5 segundos. Intervalos maiores deixam lacunas. Ao reiniciar, a leitura pendente é descartada para não cobrir a interrupção.
- **Coleta válida** informa a parte do período que efetivamente tem resposta ou perda medida. Um resultado de 100% com cobertura baixa não comprova disponibilidade de 100% durante o período inteiro. Sem tempo medido, o percentual aparece como `—`.

O histórico começa após instalar esta versão: as 720 amostras antigas não representam os últimos 30 dias e não são usadas para inventar resultados retroativos. Totais diários ficam no SQLite por 31 datas UTC, sem acumular milhões de pings individuais. Reiniciar e renomear preservam o histórico; trocar o IP/tipo reinicia o histórico desse equipamento, e removê-lo também remove seus totais. Nesta primeira etapa, o relatório cobre o ping local de BBUs, Datacoms e SIAE; pings remotos dos circuitos e portas não entram nesse percentual.

## Backups automáticos, exportação e restauração

Na aba **Backups**, o programa cria uma cópia automática na primeira execução do dia e verifica novamente a cada minuto enquanto estiver ligado. Mantém os **7 backups automáticos** mais recentes e, separadamente, os **5 manuais** mais recentes em `.data/backups/` (ou `MONITOR_DATA_DIR/backups/`). Dias em que o programa não executar não geram uma cópia. A rotação só ocorre após criar uma cópia válida. Falhas de espaço, permissão, integridade ou chave são informadas nessa aba e não param o monitoramento.

**Criar e baixar backup** gera um ZIP e inicia o download. Cada cópia também tem um botão **Baixar ZIP**. O SQLite é copiado pela API de backup, incluindo transações já confirmadas no WAL: não é uma cópia insegura do arquivo durante gravações. O ZIP contém `monitor.db`, `credentials.key` e um manifesto com versão e hashes SHA256. São verificadas a integridade do banco e a compatibilidade da chave com as credenciais criptografadas. O limite é de 512 MiB para o banco de cada cópia.

**O ZIP contém a chave de descriptografia.** Guarde em local protegido e mantenha uma cópia fora do disco do programa. Os backups não são enviados automaticamente a serviços externos. No Linux, arquivos são criados com modo 600 e pastas com 700; no Windows, proteja o acesso à pasta pelas permissões do sistema. O modo demonstração não lista, cria ou baixa backups reais.

Para restaurar, pare o programa e, na pasta do projeto, use **uma pasta nova que ainda não exista**. O utilitário valida o conteúdo, os hashes, o banco e a chave antes de criar o destino. Não sobrescreve sua pasta de dados atual.

Windows, no PowerShell (ajuste o caminho do ZIP):

```powershell
.venv\Scripts\python.exe backups.py restore "C:\caminho\backup.zip" --destination ".data-restaurada"
$env:MONITOR_DATA_DIR = "$PWD\.data-restaurada"
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Linux/macOS:

```bash
.venv/bin/python backups.py restore "/caminho/backup.zip" --destination ".data-restaurada"
MONITOR_DATA_DIR="$PWD/.data-restaurada" bash start.sh
```

Mantenha `MONITOR_DATA_DIR` apontando para a pasta restaurada em cada nova inicialização, inclusive no seu serviço ou atalho. As pastas `.data/` e `.data-restaurada*/` são ignoradas pelo Git. Nunca envie o ZIP, o banco ou a chave ao repositório. Os comandos acima também estão disponíveis na ajuda da aba Backups.

## Notificações pelo Telegram

A aba **Notificações** envia quedas e recuperações para uma **conversa, grupo ou canal do Telegram**, usando um bot. A configuração precisa somente do **token do bot** e do **Chat ID** do destino. Não exige modelo de mensagem aprovado nem conta empresarial.

### Configurar o bot e escolher o destino

1. No Telegram, abra o perfil oficial [@BotFather](https://t.me/BotFather), envie `/newbot` e siga as instruções. Copie o token fornecido pelo BotFather.
2. Na aba Notificações, informe o token e salve, ainda com alertas desativados. Não envie o token pelo chat.
3. Abra a conversa com o novo bot e envie `/start`. Para receber em grupo, adicione o bot e envie `/start@NomeDoSeuBot` no grupo. O bot precisa ter permissão para enviar mensagens; em canais, normalmente precisa ser administrador.
4. Clique em **Buscar conversas**, escolha o destino e salve. Se já souber o Chat ID, pode informá-lo diretamente. IDs de grupos normalmente são negativos: mantenha o sinal de menos. O Chat ID **não é o número do telefone**.
5. Clique em **Enviar teste** e confira o recebimento no Telegram. Esse botão envia uma mensagem real; salvar a configuração não envia um teste.
6. Marque **Ativar alertas automáticos** e salve. Apenas novos eventos entram na fila. Não há envio de eventos da demonstração nem replay do histórico anterior.

**Buscar conversas** consulta até 20 atualizações recentes do bot e retorna somente nomes, tipos e IDs das conversas, nunca o conteúdo das mensagens. A consulta não confirma/remove atualizações e não altera os filtros ou o webhook do bot. Se a conversa não aparecer, envie `/start` novamente e repita a busca. Use um bot dedicado: um webhook ou outro coletor pode impedir essa consulta; o programa não remove integrações existentes automaticamente.

O servidor precisa alcançar `https://api.telegram.org` na porta 443, mantendo a verificação TLS. O token fica criptografado no banco com a mesma chave das outras credenciais e nunca é retornado pela API. Deixe o campo vazio para manter um token já salvo. A Bot API exige o token no caminho da requisição HTTPS; erros exibidos pelo programa são tratados para não expor esse endereço nem o token, e redirecionamentos são recusados.

### Se Enviar teste recusar a conversa

O **Chat ID da conversa é diferente do ID do bot**. Não copie o número antes dos dois-pontos do token e não use o telefone como destino. Abra o bot correspondente ao token salvo, envie `/start`, volte ao painel, clique em **Buscar conversas**, selecione o destino e **salve antes de testar**. Para grupos, mantenha o sinal de menos do ID e confira se o bot é membro e pode escrever.

O programa identifica separadamente ID do próprio bot, conversa não encontrada, bot bloqueado, falta de permissão e destino que ainda não iniciou conversa. Rejeições desconhecidas mostram o código HTTP sem afirmar que o Chat ID está errado. O conteúdo bruto de erros da API e o token não são exibidos.

### Eventos, agrupamento e tentativas

- Ping: avisa a entrada na **21ª perda consecutiva** e a recuperação. Perdas adicionais na mesma sequência não geram novos eventos.
- Portas: avisa transições Down/Up, com tipo, número e nome personalizado da porta quando disponíveis.
- Circuitos: avisa queda e recuperação do ping realizado pelo Datacom.
- Erros de coleta são opcionais e vêm desmarcados, separados de perdas de ping. A opção inclui falhas de ICMP/SSH/banda SIAE e a recuperação da leitura de banda SIAE.
- A fila é persistida no SQLite na mesma transação do evento. Um serviço separado envia **até 3 eventos por resumo**, por padrão a cada **30 segundos** (ajustável entre 15 e 300). Eventos adicionais aguardam o próximo resumo. As mensagens usam o horário de Manaus (UTC−4); o armazenamento continua em UTC.
- Falhas de conexão, indisponibilidade ou limite temporário do Telegram permitem até **3 tentativas**, com espera entre elas. O prazo de repetição informado pelo Telegram é respeitado entre 30 segundos e uma hora. Erros de token ou destino pausam a fila até corrigir e salvar ou realizar um teste bem-sucedido. O monitoramento continua independente dos envios.
- Eventos com mais de **uma hora** expiram para evitar uma enxurrada de avisos antigos após uma interrupção. A fila comporta até **500 eventos**; no limite, novos eventos continuam no painel, mas não entram na fila. O histórico de envios guarda até **1.000 eventos por até 7 dias**.
- Salvar ou remover a configuração cancela envios pendentes para não enviá-los a outro destino. Uma solicitação já iniciada pode terminar no destino anterior. Uma interrupção após o Telegram aceitar a mensagem e antes de o programa registrar a resposta pode causar duplicidade em uma nova tentativa.

### Formato das mensagens

A falha mostra **🔴 nome do equipamento**, a causa e **Iniciado: data e hora**, sem cabeçalho do grupo, título adicional ou IP do equipamento. Na normalização, mostra **🟢 nome do equipamento**, a mesma causa, **Resolvido: data e hora** e **Tempo fora** em dias, horas, minutos e segundos. O início não é repetido na mensagem de resolução, mas continua salvo para calcular a duração. Os horários enviados são de Manaus (UTC−4), inclusive ao executar no Windows, sem dependência adicional de fuso horário.

O início corresponde à detecção registrada da falha: no ping, a entrada na 21ª perda consecutiva; nas portas, a leitura que identificou Down. A resolução usa o horário em que o monitor confirmou a recuperação. São horários de observação, não uma estimativa retroativa do instante físico da queda.

A causa e o início ficam persistidos por equipamento e ocorrência (ping, porta física, circuito ou banda SIAE). Reiniciar o programa ou limpar mensagens antigas da fila não perde uma ocorrência aberta. A recuperação de uma porta não fecha outras portas ou o ping do mesmo equipamento. Renomear a porta mantém a causa registrada na abertura. Remover/trocar o alvo limpa a ocorrência correspondente.

Na atualização, uma falha de ping ainda ativa pode recuperar o início pelo alerta original, se ele estiver no histórico. Ocorrências cujo início não foi registrado ou recuperado mostram **Tempo fora: não registrado** na resolução, em vez de inventar uma duração. Se o relógio de resolução for anterior ao início, mostram **Tempo fora: não disponível**. A alteração de formato não modifica os textos originais do histórico do painel nem reenvia eventos já enviados.

**Aceito pelo Telegram** indica que a Bot API retornou um ID de mensagem para o destino configurado, e não uma confirmação de leitura pelo operador. O token também entra nos backups criptografado; ao restaurar uma cópia, as notificações ficam **desativadas** e os envios pendentes da cópia são cancelados. Confira o destino antes de reativar.

Na atualização que substitui o WhatsApp, a configuração anterior é desativada, o token antigo é removido e seus envios pendentes são cancelados. Esse histórico de envio não entra nos contadores do Telegram. Cadastros, eventos de monitoramento, disponibilidade e backups são preservados.

Os testes automatizados usam respostas simuladas do Telegram e verificam fila, tentativas, migração, criptografia, seleção de conversas e isolamento da demonstração. O recebimento real deve ser confirmado pelo botão de teste após configurar o seu bot e a conectividade do servidor.

## Validação

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/pip check
node --check static/app.js
```

Os testes cobrem o limiar de 20/21 perdas, recuperação, perdas intercaladas, erro de ICMP, parser das linhas Datacom, detecção automática de portas, transições Up/Down, isolamento de interfaces, validação de entradas, criptografia, rejeição de chave SSH e remoção de amostras.

API de saúde: `GET /api/health`. API e documentação OpenAPI disponíveis no próprio servidor em `/docs`.

O teste de navegador desta implementação verificou demonstração, busca, detalhes, navegação de portas, formulário SSH, cadastro/exclusão real via API e responsividade a 390px. O ICMP real foi bloqueado pelas permissões do ambiente e não é reportado como aprovado.

### Latência por tipo de equipamento

Na Visão geral, o seletor **Equipamento** do cartão **Latência média** alterna entre BBU (cadastros de ping), Rádio SIAE e Datacom. A média e o gráfico usam apenas as amostras dos equipamentos do tipo escolhido, sem misturar categorias. A escolha inicial é Datacom e fica salva neste navegador. A média continua sendo calculada por instante; perdas não são tratadas como zero. Se o tipo não tiver equipamentos ou respostas nas últimas amostras recebidas, a média aparece como **—** com uma explicação, sem utilizar dados de outro tipo.

### Visão geral compacta

A tela inicial segue o protótipo compacto aprovado: Manrope local, fundo claro, cartões brancos com sombra suave, indicadores em uma faixa única, tabela à esquerda e atenção/latência à direita. Busca, filtros, ordenação pelas colunas e menu **···** permitem consultar e gerenciar os equipamentos. A tabela mostra localidade pelo IP cadastrado no mapa do circuito e portas ativas/consultadas; informações ausentes aparecem como **—**. Consultas SSH com erro não exibem contagens antigas de portas como atuais. O painel **Atenção agora** prioriza problemas presentes, com mensagens curtas, e abre os detalhes do equipamento.

O menu inicia recolhido para novos navegadores e preserva a preferência já salva. Em telas menores os painéis se empilham e a tabela vira cartões. O seletor de latência continua separando BBU, Rádio SIAE e Datacom. A [captura da tela compacta](docs/visao-geral-compacta.png) usa dados ilustrativos de validação.

### Rádios por trecho e rede

A aba **Rádios SIAE** organiza os cadastros em **Tefé → Tabatinga**, **Coari → Tefé · Rede 1** e **Coari → Tefé · Rede 2**. Na primeira inicialização após a atualização, os rádios existentes ficam em Tefé → Tabatinga. IDs, credenciais, históricos e telemetria são preservados. Cadastros novos de Coari → Tefé exigem escolher a rede. Os botões de cada grupo já preenchem trecho e rede no formulário; a edição permite mover um rádio entre os grupos.

Os cartões usam o selo verde **Respondendo** quando há resposta até **200 ms**, amarelo quando a latência é **maior que 200 ms**, vermelho quando o monitor declara **sem ping** e cinza sem leitura ou com erro de coleta. O estado sem ping continua respeitando a regra existente da 21ª perda consecutiva. Uma falha de coleta não é tratada como queda confirmada. Trecho/rede ficam no banco e acompanham os backups; a API também fornece `radio_status` para a futura integração ao mapa. Esta atualização organiza os rádios; o traçado dos enlaces será definido em uma próxima etapa com a sequência dos pontos.

Reinicie o programa após atualizar para aplicar a migração do banco, mantendo `MONITOR_DATA_DIR` na pasta de dados que você já utiliza. A [captura dos rádios por trecho](docs/radios-por-trecho.png) usa dados ilustrativos de validação.

### Rádios Coari → Tefé no mapa

O mapa inclui duas redes independentes no trajeto **Coari → Betânia → Aracati → Prainha → Tefé**, com quatro enlaces AP/ST em cada rede. Os nomes e os 16 IPs informados ficam em `static/backbone.json`, separados dos 28 enlaces de fibra. Cada ponta é associada ao cadastro SIAE pelo IP. Clique no ícone para abrir o rádio cadastrado ou iniciar um cadastro preenchido com nome, IP, trecho e rede; nenhuma credencial é criada automaticamente.

Uma linha de rádio fica azul com respostas atuais de ambas as pontas até 200 ms; amarela se alguma ultrapassar 200 ms; vermelha se alguma estiver sem ping. Sem cadastro, sem resposta válida, com dados antigos ou com conexão ao monitor interrompida, a linha fica cinza. O vermelho continua seguindo a regra existente do estado sem ping, após 21 perdas consecutivas. Os detalhes mostram AP e ST, latência e banda disponível; banda antiga ou com erro não aparece como atual. Essas cores são exclusivas dos enlaces de rádio; as fibras continuam usando sua própria legenda.

A aba de rádios usa cartões menores e o selo **Respondendo** verde. Informações de banda não configurada ficam resumidas com acesso a **Configurar banda**; equipamentos com banda habilitada continuam mostrando as leituras. A [captura do mapa com as duas redes](docs/mapa-com-radios.png) usa dados ilustrativos de validação.

As duas redes de rádio têm ligação visual ao Datacom de Coari (`10.200.9.1`) e ao Datacom **CLARO** de Tefé (`10.200.19.1`). A Rede 1 sai de Coari pela **Ten 1/1/8** e a Rede 2 pela **Ten 1/1/9**; essas conexões usam as leituras das respectivas portas e do rádio AP. Na chegada ao CLARO, as portas candidatas são **Giga 1/1/5, 1/1/6, 1/1/7 e 1/1/8**, sem atribuição confirmada por rede. Por isso a chegada fica tracejada, com a porta pendente explícita nos detalhes, mesmo que alguma candidata tenha leitura. As curvas de acesso identificam as conexões com os Datacoms; cruzamentos sem ponto de junção não unem redes nem fibras.

### Abas de equipamentos somente em cartões

As abas **BBUs**, **Rádios SIAE** e **Datacoms** mostram somente cartões, sem repetir a lista de equipamentos acima. Busca por nome/IP e filtro de estado ficam acima dos cartões. BBUs exibem estado, IP, latência, perdas e última checagem; rádios preservam os grupos por trecho/rede e os controles de banda; Datacoms preservam os cartões de portas e circuitos. Cada equipamento mantém acesso a editar, ver detalhes e remover com confirmação. A atualização automática preserva o foco nos botões dos cartões. A tabela compacta da Visão geral continua sendo a visão consolidada da rede. As capturas de [BBUs](docs/bbus-cartoes.png) e [rádios](docs/radios-por-trecho.png) usam dados ilustrativos de validação.

Os painéis de BBUs, rádios e Datacoms seguem o mesmo padrão compacto: busca e filtro dentro do cabeçalho do painel, controles de 36 px, cartões com largura flexível a partir de 220 px no computador e uma coluna em telas pequenas, com fontes e espaçamentos consistentes. A aba **Backbone Veloso NOC** usa um ícone de topologia próprio. A [captura dos Datacoms](docs/datacoms-cartoes.png) mostra esse padrão com dados ilustrativos.

As grades distribuem as colunas por toda a largura disponível do painel, com intervalo de 12 px. Linhas completas ficam alinhadas à borda direita; a última linha mantém o mesmo tamanho de cartões das anteriores, sem esticar os poucos equipamentos restantes.

### Rota de rádios Tefé → Tabatinga

O Backbone Veloso NOC inclui os **15 enlaces AP/ST** informados em sequência, com os **30 IPs de 192.168.60.1 a 192.168.60.30**. O desenho segue Tefé, Uarini, Tamanicuá, Fonte Boa, Monte Sião, Jutaí, Guariba / N. Progresso, Prosperidade, Tonantins, Santo Antônio, Amaturá, Caturiá, São Paulo, Santa Rita, Belém do Solimões e Tabatinga. Guariba e N. Progresso foram confirmados como o mesmo ponto; o nome do receptor 192.168.60.24 foi invertido para **ST_SAO_PAULO/CATURIÁ**, conforme confirmado. Os demais nomes foram preservados.

No seletor **Trecho**, escolha **Tefé → Tabatinga** para ampliar essa rota, **Manaus, Coari e Tefé** para o backbone anterior ou **Todos os trechos** para o conjunto completo. A seleção fica salva no navegador. O trecho aparece em uma única linha, com Tefé à direita e Tabatinga à esquerda; os pontos agrupam os rádios da mesma localidade. Cada enlace usa as leituras de seus próprios AP e ST, com azul até 200 ms, amarelo acima de 200 ms, vermelho para sem ping e cinza sem leitura atual. Clique em um rádio para abrir o cadastro existente pelo IP ou iniciar um cadastro já preenchido no trecho Tefé → Tabatinga. A [captura da rota até Tabatinga](docs/radios-tefe-tabatinga.png) usa dados ilustrativos.

A origem da rota **Tefé → Tabatinga** está ligada visualmente ao Datacom **Tefé CLARO (`10.200.19.1`)**, seguindo para **AP_TEFE/UARINI (`192.168.60.1`)**. A porta dessa saída ainda está **a confirmar** e não foi associada às Giga 5–8 das chegadas de Coari. Enquanto não for identificada, essa ligação permanece tracejada/cinza e informa a pendência nos detalhes, sem alterar as leituras dos 15 enlaces de rádio.

### Visualização horizontal do backbone

O desenho usa faixas horizontais como a referência fornecida: fibra na parte superior, duas redes Coari → Tefé no meio e os 15 enlaces Tefé → Tabatinga em uma única linha inferior. Coari aparece à esquerda e Manaus à direita no backbone; o trecho inferior segue de Tefé, à direita, até Tabatinga, à esquerda. Os dados de equipamentos, IPs e portas permanecem os mesmos. Cada ponto de rádio agrupa AP e ST da localidade; clique no ponto para consultar os dois equipamentos, ou na linha para os detalhes do enlace. Os 46 rádios continuam associados individualmente pelo IP.

O mapa ocupa toda a largura disponível. **Ajustar à largura** preserva essa escala e permite rolagem vertical quando a tela for mais baixa, sem encolher todo o desenho pela altura. **Tela cheia** amplia a área de trabalho, mantendo os detalhes, cadastros e portas pendentes acessíveis. No modo Tráfego, o valor principal é o RX do AP/porta de origem quando disponível; a leitura das duas pontas continua nos detalhes e no modo Todos os detalhes. Sem banda válida nos rádios, o mapa mostra ping ou o estado sem leitura. A [captura do mapa horizontal](docs/mapa-horizontal.png) usa dados ilustrativos de validação.

No celular, o desenho inicia ampliado para navegação por arraste; o botão Ajustar à largura permite escolher uma visão geral menor quando desejado.

A visualização do backbone prioriza o desenho: o título completo fica no caminho de navegação, os controles ocupam uma faixa compacta e o resumo de leituras fica no rodapé junto à legenda. A área do mapa preenche a altura restante da janela. Essa preferência visual não altera a tela inicial do sistema.

A INFOVIA Coari → Escritório Tefé sai da Ten 1/1/7 de Coari e chega espelhada na Ten 1/1/4 do Escritório. Essa chegada é compartilhada com a INFOVIA de Manaus e está identificada nos detalhes dos dois enlaces. A leitura de chegada não representa banda exclusiva de cada transporte; o modo Tráfego continua exibindo a porta de origem de cada rota.

### Huawei S6730 / VRP

No mapa, clique em Manaus (10.200.1.1) para abrir o cadastro SSH já preenchido com as portas 0/0/11, 0/0/12 e 0/0/23. Se o IP já existir como BBU/ping, o mesmo cadastro é aberto para conversão; salvar conserva seu ID. Também há o botão **Usar Huawei S6730 · portas 11, 12 e 23** no formulário SSH. Informe usuário, senha e impressão digital SHA256 verificada diretamente no formulário. A configuração é salva somente ao confirmar o cadastro.

O coletor consulta `display interface XGigabitEthernet {port}` e `display transceiver interface XGigabitEthernet {port} verbose`. A banda RX/TX vem das taxas médias `Last 300 seconds`, identificadas no cartão; picos, contadores de bytes e limites ópticos não viram medições atuais. Falhas SSH continuam invalidando as leituras anteriores. Os vínculos atualizados são Huawei XGE0/0/11 → Limão Ten 1/1/1 e Huawei XGE0/0/12 → Limão Ten 1/1/2. A marcação antiga de reparo foi removida do modelo; marcações manuais salvas em Editar portas / manutenção continuam sob controle do operador.

A consulta Huawei usa um único terminal SSH interativo por coleta, reconhece o prompt VRP e avança a paginação automaticamente. Cada comando tem espera limitada a 20 segundos. Em timeout, o diagnóstico informa o comando executado e conserva somente a saída parcial como diagnóstico, sem publicá-la como leitura atual. A conexão mantém a validação da impressão digital cadastrada.

A origem da INFOVIA Manaus → Escritório Tefé foi corrigida para o Huawei 10.200.1.1, XGigabitEthernet0/0/23; a chegada continua Ten 1/1/4. No cadastro existente do Huawei, use **Usar Huawei S6730 · portas 11, 12 e 23** e salve para incluir a Ten 23 na coleta. O vínculo antigo do Datacom 2 foi substituído, evitando aplicar suas portas manuais à nova origem Huawei.

O desenho compacta as faixas de rádio e o espaço até Tabatinga, além de distribuir Sodré, Codajás e Anori mais perto de Coari. A escala dos ícones e das letras é mantida; os filtros de trecho usam os mesmos limites compactos.

As fibras paralelas usam curvas mais afastadas e as rotas via Nazaré e via KM60 ficam em faixas distintas. O segmento Anori → Coari é compacto. Em Tefé, os nomes ficam à direita dos equipamentos, as fibras chegam pela esquerda e as saídas dos rádios partem por baixo; as leituras da fibra local e da interligação Manaus têm posições próprias.
