# VELOSONET MONITORAMENTO

Primeira versão de um painel local para monitorar ping e interfaces de equipamentos Datacom por SSH. Interface em português, responsiva, com identidade VELOSONET e tema azul-marinho. Textos claros e indicadores em verde, vermelho e âmbar destacam os estados dos equipamentos. Não requer etapa de compilação ou serviços de fontes externos. Python 3.12+, FastAPI, SQLite e JavaScript.

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
