# Eleições ao Vivo — guia do projeto e manual de uso

Painel **não oficial** da apuração das eleições brasileiras de 2026, em Python + Flask, sobre os arquivos públicos de
divulgação de resultados do TSE. Repositório público: `github.com/luukas20/eleicoes-ao-vivo` (licença MIT).
O [README.md](README.md) é a versão curta e pública; este arquivo é o guia completo para quem opera ou mexe no projeto
(inclusive o Claude). Idioma de tudo: **português do Brasil** (interface, comentários, nomes no código).

Estado em 25/10/2026: 1º turno (04/10) encerrado; 2º turno em 25/10. O portal foi **aprovado pelo usuário** (identidade
visual, Presidente, Governador, Senador, três cargos de deputado, municípios, gráfico, tema escuro, celular). Último commit
relevante: publicado na `main` do GitHub; a tag prevista é `v0.4.0` e ainda não foi criada.

---

## 1. Regras de ouro (leia antes de agir)

1. **Não altere o portal sem pedido explícito.** O dono do projeto considera o portal pronto e pediu para não mexer nele.
   Pedidos de avaliação, estimativa ou teste são **só leitura**: leia o código e meça numa cópia descartável fora do
   projeto (`PYTHONDONTWRITEBYTECODE=1`, dados na pasta temporária da sessão, escutando só em `127.0.0.1`), confira que
   `git status` está limpo no fim e desligue tudo o que ligou. Melhorias entram como texto de recomendação.
2. **Nunca exponha o computador que roda o painel à internet sem pedido explícito** (túnel Cloudflare, abrir porta no roteador,
   `HOST=0.0.0.0` etc.). O dono do projeto prefere não deixar o computador exposto sem necessidade. O
   classificador de permissões do Claude Code **bloqueia túneis públicos**; não tente contornar. Se for necessário,
   explique e deixe o usuário liberar a regra de permissão ou rodar o comando por conta própria (seção 2.7).
3. **Seja educado com o TSE.** O limite deles é 100 requisições/s por IP, o bloqueio dura 10 minutos e **se renova a
   cada nova tentativa**; URLs inexistentes (404) repetidas também bloqueiam. Use sempre o `TseClient` do projeto
   (taxa limitada, GET condicional, disjuntor) e só peça URLs derivadas do arquivo de configuração. Nunca faça
   varreduras ou laços de requisições à mão; testes usam os arquivos reais capturados em `tests/fixtures/`.
4. **Fidelidade dos dados.** Números do TSE aparecem exatamente como publicados (percentuais com vírgula etc.); o que o
   painel calcula é rotulado como cálculo do painel ("% dos votos válidos" dos agrupamentos, diferença em p.p., soma
   das seções das UFs). Vagas de deputados são **provisórias** até a totalização final (como o TSE publica) e "Eleito"
   só aparece quando o próprio TSE marca; o painel nunca decide quem se elegeu.
5. **Nada de dependências externas no navegador.** A CSP é estrita (`default-src 'self'`; sem CDN, sem script ou
   estilo inline). Fontes (Archivo e DM Mono) são servidas pelo próprio painel. Todo texto vindo de arquivos externos
   entra no DOM por `textContent` (helpers `h()` e `svg()` em `app/static/js/dom.js`); `innerHTML` só para os ícones
   estáticos.
6. **Git:** commit e push **somente quando o usuário pedir**. Mensagens no estilo `feat: ...` / `fix: ...` em
   português, seguidas da linha de coautoria que a sessão indicar.
7. **Windows.** O shell principal é o PowerShell; a ferramenta Bash é o Git Bash. Caminhos que começam com `/` (como
   `/status`) viram caminhos do Git: use `MSYS_NO_PATHCONV=1` ao passar URLs a scripts. Scripts longos com aspas
   complicadas: grave o arquivo e rode, em vez de usar here-doc. Esperas longas: laço `until` ou tarefa em segundo
   plano, nunca `sleep` em primeiro plano.
8. **Terminal novo para a apuração real.** Se o mesmo terminal foi usado para ensaiar com o simulador, as variáveis
   `TSE_BASE`, `TSE_AMBIENTE` e `ESCALA_POLLING` continuam definidas e o painel real subiria apontando para o
   simulador. Abra um terminal novo (ou limpe as variáveis, seção 2.8).

---

## 2. Manual de uso

### 2.1 Requisitos e instalação

- Windows 10/11, Python 3.12+, internet. Chrome instalado só para os testes de interface.
- Uma vez, na pasta do projeto (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt            # só o painel
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt        # + testes (pytest, Playwright, axe)
```

### 2.2 Subir o painel real (passo a passo)

1. **Abra um terminal PowerShell novo, na pasta do projeto.** No VS Code: menu *Terminal > Novo Terminal* (já abre na
   pasta). Ou, no Explorador de Arquivos, abra a pasta do projeto, clique na barra de endereço, digite `powershell` e
   Enter. Terminal **novo** porque um terminal antigo pode ter variáveis do simulador (seção 1, item 8). Para conferir:
   `Get-ChildItem Env:TSE_*` não deve listar nada.

   **Atenção ao tipo de terminal.** Os comandos deste manual são do **PowerShell** (o prompt começa com `PS C:\...>`).
   Se o seu prompt for só `C:\Users\seu-usuario>` você está no **Prompt de Comando (cmd)**: digite `powershell` e Enter para
   trocar, ou use as versões para cmd indicadas em cada passo (o `&` que aparece nos comandos do PowerShell **não existe**
   no cmd e dá "& foi inesperado neste momento"). No cmd, para conferir variáveis antigas: `set TSE_` (não deve listar nada).
2. **Rode o painel** (PowerShell; no cmd troque a primeira linha por `cd /d "<pasta do projeto>"`; nos dois, troque `<pasta do projeto>` pelo caminho da pasta onde o projeto está):

```powershell
cd "<pasta do projeto>"
.venv\Scripts\python.exe run.py
```

3. **O que deve aparecer** em poucos segundos (a janela fica "ocupada": é o painel rodando):

```
Painel em http://127.0.0.1:8000  | fonte: https://resultados.tse.jus.br/oficial
... INFO waitress: Serving on http://127.0.0.1:8000
... INFO poller: configuração do TSE (idg ...): 181 alvos
```

4. **Confirme no navegador:** <http://127.0.0.1:8000> mostra o chip "Ao vivo · atualizado há N s" e **não** mostra a faixa
   amarela "DADOS SIMULADOS". Em <http://127.0.0.1:8000/status>, "arquivos carregados" chega ao total de alvos em
   cerca de 30 segundos e "Alvos com problema" fica em 0.
5. **Deixe a janela aberta.** Ela é o painel: fechar a janela (ou `Ctrl+C` nela) desliga o painel. Os eventos
   (mudança de configuração, erros) aparecem nela e também ficam em `data\logs\painel.log`.

O painel consulta sozinho o feed oficial (`https://resultados.tse.jus.br/oficial`) e descobre as eleições pelo arquivo de
configuração do TSE; o segundo turno entra sozinho. Para rodar **sem janela** (como o Claude faz): `Start-Process
-WindowStyle Hidden` com `.venv\Scripts\python.exe run.py`, guardando a saída em arquivos (sem janela o erro some); nesse
caso o processo aparece só no Gerenciador de Tarefas (aba Detalhes: `python.exe`) e se para com os comandos da seção 2.8.

**Configuração:** só por **variáveis de ambiente** (o arquivo `.env` existe como modelo, mas o painel **não o lê**).

| Variável | Padrão | Para que serve |
|---|---|---|
| `TSE_BASE` | `https://resultados.tse.jus.br` | Origem do feed (o simulador usa `http://127.0.0.1:5001`) |
| `TSE_AMBIENTE` | `oficial` | `oficial` ou `simulado`; também nomeia a pasta do histórico |
| `TSE_ELEICOES` | vazio | Lista de códigos para forçar (vazio = descobrir pelo EA11) |
| `CARGOS` | `1,3,5,6,7,8` | Presidente, Governador, Senador, Dep. Federal, Estadual, Distrital |
| `USER_AGENT` | identifica o projeto | Boa prática perante o TSE |
| `MAX_RPS` | `15` | Teto de requisições/s ao TSE (o limite deles é 100) |
| `WORKERS` | `8` | Threads do poller |
| `ESCALA_POLLING` | `1.0` | Multiplica os intervalos de consulta (use < 1 **só** com o simulador) |
| `DESATUALIZADO_APOS_S` | `120` | Segundos sem consulta bem-sucedida até o aviso na tela |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Onde o painel escuta; `HOST=0.0.0.0` abre para a rede local |
| `DATA_DIR` | `data/` do projeto | Histórico, fotos e logs |
| `INICIAR_POLLER` | `1` | `0` não consulta o TSE (testes) |

### 2.3 Páginas

| Endereço | O que mostra |
|---|---|
| `/` | Presidente: manchete gerada pelos números, duelo dos dois primeiros com foto, faixa de participação (marca de 50%), andamento, mapa (ou blocos), ranking, gráfico de evolução e tabela por UF |
| `/governadores`, `/senadores` | Mapa pelo partido de quem lidera, tabela com todas as UFs |
| `/deputados-federais`, `/deputados-estaduais` | Hemiciclo, bancadas somadas, mapa pelo partido ou federação mais votado, tabela por UF (o estadual inclui o Distrital do DF) |
| `/uf/<uf>` | Abas: Presidente, Governador, Senador e os deputados da UF (no DF, Distrital no lugar do Estadual); busca de municípios |
| `/municipio/<uf>/<código>` | Presidente, Governador e Senador no município (consultado sob demanda) |
| `/status` | Diagnóstico: consultas ao TSE, camadas, arquivos com problema, disjuntor e **acessos ao painel** (seção 3.9) |
| `/healthz` | `{"ok": true}` para verificar se o painel está de pé |

Parâmetros de URL: `?turno=1|2` (turno exibido) e `?intervalo=<ms>` (intervalo de consulta do navegador, de 2000 a
120000; usado em testes e telões; o padrão é 10 s e o gráfico usa 15 s). O botão de tema (lua/sol) e a escolha
Mapa | Blocos ficam salvos no navegador (`tema`, `mapa-visao` no `localStorage`).

O chip no topo diz o estado: "Ao vivo · atualizado há N s", "Sem atualização do TSE há N" (mais de
`DESATUALIZADO_APOS_S` sem resposta), "Consultas ao TSE pausadas" (disjuntor aberto) ou "Sem conexão com o servidor do
painel" (o navegador não alcança o painel). A faixa amarela "DADOS SIMULADOS" só aparece quando a fase dos arquivos é
simulada; no ambiente real ela não deve aparecer nunca.

### 2.4 Primeiro e segundo turno

- A tela inicial mostra o **1º turno até a apuração do 2º começar**; depois passa sozinha para o 2º (regra
  `turno_padrao()`: o maior turno cuja apuração já começou). O seletor "1º turno | 2º turno" fica no topo enquanto
  houver os dois.
- Em 25/10/2026 o feed real traz **Presidente** (eleição 6258: Lula x Flávio Bolsonaro, 28 UFs) e **Governador** (6260:
  AM, RN, DF, ES, AC, TO). **Senador e deputados só existem no 1º turno** e continuam abertos no padrão (o painel cai
  no 1º turno para esses cargos); pedir `?turno=2` para eles dá erro claro (404).
- O histórico do gráfico é separado por eleição (6257/6259 no 1º turno, 6258/6260 no 2º).

### 2.5 Ver no celular

- **Mesma rede Wi-Fi:** reinicie o painel com `HOST=0.0.0.0` (`$env:HOST="0.0.0.0"` no terminal), descubra o IP do
  notebook com `ipconfig` (ex.: `192.168.x.x`) e abra `http://<IP>:8000` no celular. O Windows pode pedir permissão no
  firewall (já existe regra para o Python em redes "Públicas"). O celular não pode estar nos dados móveis, em rede de
  convidados nem com VPN; alguns roteadores isolam os aparelhos entre si. Enquanto estiver assim, qualquer pessoa na
  mesma rede abre o painel. Volte para `127.0.0.1` ao terminar.
- **Dados móveis ou outra rede:** exige um túnel (seção 2.7) ou uma VPN privada (Tailscale). O endereço da rede local
  não funciona fora de casa.

### 2.6 Noite da apuração (checklist)

1. **Antes:** notebook na tomada, sem suspensão (ligado na tomada o Windows costuma não suspender; confira o plano de energia e o que
   fechar a tampa faz), de preferência no cabo de rede, sem atualização do Windows agendada. Terminal novo.
2. Subir o painel (2.2) **antes** de a apuração começar: o histórico do gráfico só existe porque o painel registra cada
   totalização; quem liga depois perde o começo da curva.
3. Conferir `/status`: todos os alvos carregados, `com problema` zerado, disjuntor fechado, e `/` mostrando "Ao vivo".
   Antes de a apuração começar aparece "A apuração ainda não começou"; o resultado do Presidente só é liberado a partir
   das 17h de Brasília (Res. TSE 23.751/2026, art. 265 §1).
4. Durante: abrir de vez em quando. Se o "atualizado há" passar de ~2 minutos, veja a seção 2.9.
5. Depois: o histórico fica em `data/historico/oficial/` (pode ser guardado); desligar tudo (2.8).

### 2.7 Colocar no ar com link público (túnel), passo a passo — só com autorização do usuário

Para o celular nos dados móveis (ou qualquer pessoa na internet) abrir o painel que roda no notebook. São **duas janelas do
PowerShell abertas ao mesmo tempo**: uma com o painel, outra com o túnel. Não precisa abrir porta nem mexer no roteador.

1. **Janela 1, o painel:** siga a seção 2.2 até o passo 4 (painel respondendo em <http://127.0.0.1:8000>).
2. **Janela 2, o túnel:** abra *outro* terminal PowerShell (pode ser em qualquer pasta) e rode:

```powershell
& "$env:LOCALAPPDATA\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

   No **Prompt de Comando (cmd)** (prompt `C:\Users\seu-usuario>`), sem o `&` e com `%...%` no lugar de `$env:...`:

```
"%LOCALAPPDATA%\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

3. **Copie o link.** Em 5 a 10 segundos aparece uma caixa como esta; o endereço `https://...trycloudflare.com` é o link
   público (as palavras mudam a cada vez):

```
Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):
https://exemplo-de-palavras-aleatorias.trycloudflare.com
```

   Linhas seguintes com `Registered tunnel connection` mostram que o túnel conectou. A janela fica "ocupada": deixe-a aberta.
4. **Teste:** abra o link no navegador do computador e depois no celular **com o Wi-Fi desligado** (assim o teste usa os
   dados móveis). A página deve abrir igual à do endereço local, com "Ao vivo".
5. **Compartilhe** o link. Quem acessa aparece em `/status`, no quadro "Acessos ao painel", coluna "Pelo link público".

**Regras que explicam o comportamento do link**

- **Ordem:** o painel primeiro, o túnel depois. O painel pode ser reiniciado (`Ctrl+C` e rodar de novo na janela 1) **sem
  mudar o link**; o túnel só precisa que o painel esteja de pé em `127.0.0.1:8000` quando alguém abrir.
- **O link vive enquanto a janela 2 estiver aberta e o computador ligado.** Fechou a janela, parou o processo ou reiniciou
  o PC: o link morre e o túnel novo gera **outro**. Com o túnel rápido não há como escolher nem recuperar o endereço. Para
  um endereço fixo é preciso um túnel nomeado com domínio próprio (Cloudflare), ou Tailscale Funnel, ou ngrok.
- **Mantenha o painel em `127.0.0.1`** (padrão). Não use `HOST=0.0.0.0` junto com o túnel.

**Se o `cloudflared.exe` não existir** em `%LOCALAPPDATA%\cloudflared\`: baixe `cloudflared-windows-amd64.exe` da página oficial
<https://github.com/cloudflare/cloudflared/releases/latest>, salve como `cloudflared.exe` nessa pasta e confira:
`(Get-FileHash $env:LOCALAPPDATA\cloudflared\cloudflared.exe -Algorithm SHA256).Hash` deve bater com o SHA-256 mostrado na
página da release, e `(Get-AuthenticodeSignature $env:LOCALAPPDATA\cloudflared\cloudflared.exe).Status` deve ser `Valid`
(assinante "Cloudflare, Inc."). Versão usada até aqui: 2026.9.3.

**Problemas comuns do túnel**

| Sintoma | Causa | O que fazer |
|---|---|---|
| Link abre "502 Bad Gateway" | O painel (janela 1) não está rodando | Subir o painel (2.2); o link continua o mesmo |
| Link não abre ou "Error 1033" | O túnel (janela 2) caiu ou foi fechado | Rodar o túnel de novo: o link será **novo** |
| O túnel mostra erro de conexão com a Cloudflare | Sem internet, ou a rede bloqueia o protocolo QUIC | Conferir a internet; tentar acrescentar `--protocol http2` ao comando |
| Funciona no PC e não no celular | O celular ainda está no Wi-Fi errado, ou o link foi digitado com erro | Desligar o Wi-Fi do celular e copiar o link inteiro |

**Riscos (resumo; detalhes na conversa de 25/10/2026):** o link é **público e sem login**; o túnel rápido é "só para testes"
segundo a Cloudflare (até 200 requisições simultâneas, sem garantia de disponibilidade, e alguns filtros desconfiam do
domínio `trycloudflare.com`); a página `/status` também fica pública; e tudo depende do notebook (energia, Wi-Fi, Windows
Update). Se o Claude iniciar o túnel por você, ele roda **sem janela** e o sistema de permissões do Claude Code pode
bloquear: nesse caso rode você mesmo, como acima.

### 2.8 Parar tudo

```powershell
# o painel (porta 8000) e, se houver, o túnel
$id = (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess
if ($id) { Stop-Process -Id $id -Force }
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
# limpar variáveis do simulador no terminal atual
foreach ($v in "TSE_BASE","TSE_AMBIENTE","ESCALA_POLLING","DATA_DIR","PORT","HOST","CARGOS") { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
```

Ao parar, o log pode registrar duas vezes `falha no agendador ... cannot schedule new futures after shutdown`: é uma
corrida benigna do desligamento, não um erro de funcionamento.

### 2.9 Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "Sem conexão com o servidor do painel" | Painel parado, terminal fechado, PC suspenso | Subir o painel de novo (2.2); o histórico é recarregado do disco |
| "Sem atualização do TSE há N" | O TSE ou a internet ficou sem responder por mais de 2 min | Ver `/status` (códigos, erros); o painel segue mostrando o último dado e volta sozinho |
| "Consultas ao TSE pausadas" | Disjuntor aberto: 403/429 (pausa de 11 min) ou mais de 10 respostas 404 em 1 minuto (pausa de 2 min) | **Aguardar.** Reiniciar o painel repetidamente renova o bloqueio. `/status` mostra o motivo |
| Painel mostra dados simulados ou não conecta | Variáveis do simulador no terminal | Terminal novo ou limpar as variáveis (2.8) |
| `Address already in use` / porta 8000 ocupada | Outro painel rodando | Achar o dono com `Get-NetTCPConnection -LocalPort 8000` e parar (2.8) |
| Gráfico sem curva ou com buraco | O painel não estava rodando naquele período | Não há como recuperar: o TSE só publica o estado atual |
| `A apuração ainda não começou` | Normal antes de chegarem os boletins | Aguardar |
| Link `trycloudflare.com` dá 502 ou 1033 | Túnel caiu ou painel parado | Subir o painel; se o túnel morreu, o link antigo não volta (gera-se outro) |
| Celular não abre pelo IP da rede | Wi-Fi diferente, dados móveis, firewall, `HOST` ainda em `127.0.0.1` | Conferir 2.5 |
| Foto aparece como silhueta | Candidato sem foto, ou o TSE ainda não serviu (lembrança de 404 por 10 min) | Aguardar; o painel só busca fotos de candidatos que aparecem nos arquivos |
| Muitos erros de conexão sob carga alta no Windows | O servidor fecha a conexão após cada resposta 304; em centenas de req/s as portas temporárias do Windows se esgotam | Não rode testes de carga com conexões curtas em massa; ver seção 6.4 |
| Testes e2e: "Chrome indisponível" | Chrome não instalado | Instalar o Google Chrome (os testes usam o do sistema) |

---

## 3. Arquitetura

```
TSE (CDN) ──GET condicional──▶ poller (thread) ──▶ Store (memória) ──▶ Servico ──▶ API JSON (ETag) ──▶ navegadores
                                     │                                   ▲
                                     └─ Histórico (JSONL em disco) ──────┘        páginas HTML + JS (sem CDN)
```

- **Só o servidor fala com o TSE.** Os navegadores falam apenas com a API do painel, que responde da memória; a carga
  sobre o TSE (~3 req/s no total) **não depende de quantos visitantes** há.
- Processo único: Flask + waitress (8 threads) + o poller em segundo plano. Nada de banco de dados: o estado é o
  último arquivo de cada alvo, em memória, mais o histórico e as fotos em disco.

### 3.1 Mapa de arquivos

| Caminho | Papel |
|---|---|
| `run.py` | Entrada: logs (terminal + `data/logs/painel.log`, rotativo 2 MB × 5), `create_app`, waitress |
| `app/__init__.py` | Fábrica do app, cabeçalhos de segurança (CSP etc.), liga poller, histórico e fotos |
| `app/config.py` | `Settings` a partir de variáveis de ambiente |
| `app/catalog.py` | Do EA11 às **disputas** (eleição, turno, cargo, UFs) e aos **alvos** (arquivos a consultar) |
| `app/poller.py` | Agendador por camadas, GET condicional, detecção de mudança por hash, recuos, sob demanda |
| `app/store.py` | Snapshots imutáveis em memória, chaves `cfg`, `cm:`, `ab:`, `u:<ele>:<cargo>:<abr>[:<mun>]`, `e:` |
| `app/servico.py` | Regras de negócio: monta as respostas da API (painéis, tabelas, deputados, evolução, municípios) |
| `app/api.py` | Rotas `/api/v1/...`, ETag, cabeçalhos de frescor |
| `app/views.py` | Páginas HTML, 404 amigável, rota de fotos, `/healthz` |
| `app/historico.py` | Série temporal por disputa (JSONL), recarregada ao reiniciar |
| `app/acessos.py` | Contagem de acessos ao painel (páginas, requisições, pessoas online, picos), sem guardar IP |
| `app/fotos.py` | Cache em disco das fotos (uma ida ao TSE por foto) |
| `app/cores.py`, `app/partidos.py` | Cor de cada partido e resolução de colisões |
| `app/tse/client.py` | Cliente HTTP educado: token bucket, GET condicional, **disjuntor** |
| `app/tse/urls.py` | Monta as URLs do feed a partir da configuração (nunca fixas) |
| `app/tse/parse.py` | Interpreta EA11, EA12, EA14/15, EA20 e EA10 para o modelo do painel |
| `app/tse/dominio.py` | UFs, cargos (`CARGOS`, slugs, tipo majoritário/proporcional) |
| `app/templates/`, `app/static/` | HTML, CSS (`app.css`, `partidos.css` gerado), JS em módulos ES, fontes, imagens, `data/mapa-ufs.json` |
| `mock/` | Simulador do TSE (dados fictícios) com as mesmas URLs e formatos |
| `tools/` | `capture.py`, `gerar_css_partidos.py`, `gerar_mapa.py` |
| `tests/` | Unitários e de interface; `fixtures/tse/` tem arquivos **reais** do TSE sem alteração |
| `ref/` | PDFs técnicos do TSE (EA10, 11, 12, 14, 15, 20, instruções de download, verificação JWS) |
| `data/` | Dados de execução (ignorado pelo git): `historico/<ambiente>/`, `fotos/`, `acessos/<ambiente>.json`, `logs/` (`cores/` é resto de versão antiga) |

### 3.2 Poller (consulta ao TSE)

Camadas, com intervalo mínimo e máximo por arquivo (o intervalo respeita o `max-age` que o CDN manda e recua quando
nada muda):

| Camada | Alvos | Intervalo |
|---|---|---|
| `config` | EA11 (`ele-c.json`) | 45–120 s |
| `nacional` | Presidente Brasil + acompanhamento Brasil | 8–20 s |
| `uf` | Presidente, Governador e Senador por UF | 15–45 s |
| `uf_lento` | Deputados por UF (arquivos de ~100–300 KB) | 30–90 s |
| `estatico` | Municípios (EA12) | 300–900 s |
| `sob_demanda` | Município em foco enquanto houver visitante (máx. 120 ao mesmo tempo) | 20–60 s |

- Mudança de arquivo é detectada pelo **hash do conteúdo**, não pelo `idg` (o TSE regenera arquivos sem mudar números).
- Arquivo ainda inexistente (404): não insiste por 5 minutos.
- O disjuntor global abre com 403/429 (11 min) ou excesso de 404 (2 min) e todas as consultas param.
- O painel só pede URLs derivadas da configuração/EA12: **zero 404** no feed real.

### 3.3 API, ETag e frescor

- Respostas de dados levam `ETag` (md5 do JSON): entre uma totalização e outra o navegador recebe 304. O servidor
  ainda monta o JSON para comparar; o 304 poupa banda, não CPU.
- Cabeçalhos em **todas** as respostas, inclusive 304: `X-Defasagem-S` (idade da última confirmação do TSE),
  `X-Desatualizado` (0/1), `X-Disjuntor` (0/1). O chip da tela vive deles. `Cache-Control: no-cache`.
- `Servico.disputa(slug, turno)`: sem `turno` explícito e sem disputa no turno padrão (Senador, deputados), cai no
  único turno existente; `turnos_do_cargo()` esconde o seletor nesses cargos.

### 3.4 Histórico do gráfico

- Só Presidente, Governador e Senador, para o Brasil e cada UF (83 séries no 1º turno de 2026). Arquivos
  `data/historico/<ambiente>/u_<eleição>_<cargo>_<abrangência>.jsonl`; um ponto por linha:
  `{t, st, ts, pst, vv, c: {sq: [votos, pct]}}`.
- Entra ponto novo só quando seções ou votos mudam; a série recomeça se as seções caem abaixo de metade do último
  ponto; teto de 20.000 pontos por série. O gráfico amostra no máximo 600 pontos (resposta ≤ ~90 KB).
- `simulado` e `oficial` nunca se misturam (pastas separadas).

### 3.5 Deputados (cargos proporcionais)

- EA20 por UF: `carg[0].agr[]` (partido isolado `i` ou federação `f`) → `par[]` → `cand[]`. `vag` (vagas do
  agrupamento) é **provisório até a totalização final**; `e`/`st` ("Eleito por QP", "Eleito por média", "Suplente",
  "Não eleito") só vêm depois da totalização final; `cand.dvt` ("Anulado sub judice") aparece depois da 1ª parcial e a
  lista de candidatos o explica; `qe` (quociente eleitoral) vem 0 antes da apuração. Em partido isolado os totais
  `tvtn/tvtl` não existem no `agr`: somam-se os dos `par`.
- Serviço: `painel_proporcional`, `buscar_candidatos_proporcional` (nome sem acento, número por prefixo, filtro por
  agrupamento, 20 por página), `tabela_proporcional` (soma das UFs; o estadual junta o Distrital do DF). Agrupamentos
  são guardados em cache por arquivo.
- Cor de agrupamento: a do partido mais conhecido da federação (`partidos.partido_representante`, ordem
  `PRIORIDADE`); dentro de uma UF, cores parecidas são separadas por `cores.atribuir` (campo `cor`); entre UFs vale a
  cor estável do partido (`cor_partido`).
- Front: `hemiciclo.js` (assentos em fileiras concêntricas, entregues por ângulo para formar fatias), `deputados.js`
  (manchete, tabelas, lista com busca e "mostrar mais", `PainelProporcional`), `proporcional.js` (páginas nacionais).

### 3.6 Cores dos partidos

- Tabela em `app/partidos.py` (cor clara, escura e uma variante clara/escura por partido; reservas `r1..r6`;
  `NEUTRO`). `cor` = cor da disputa (pode ser a variante, se dois partidos parecidos disputam o mesmo cargo); `cor_partido`
  = cor fixa do partido, usada nas visões que cruzam UFs.
- O CSS `app/static/css/partidos.css` é **gerado**: depois de mexer em `partidos.py` rode
  `python -m tools.gerar_css_partidos` (`--conferir` só confere; há teste que falha se estiver desatualizado). No HTML a
  cor entra por `data-cor="<chave>"` (define `--cor` e `--sobre`).

### 3.7 Front-end

- Páginas: `base.html` (barra de status, marca "Eleições 2026 ao vivo", navegação fixa, rodapé) + `painel`, `cargo`,
  `proporcional`, `uf`, `municipio`, `status`, `erro`. O módulo de cada página é `static/js/<pagina>.js`.
- Componentes em `componentes.js` (avisos, andamento, indicadores, ranking, mapa em blocos, legenda, tabela de UFs),
  `placar.js` (manchete + duelo), `mapa.js` (mapa geográfico SVG + alternância Mapa | Blocos), `grafico.js`
  (evolução), `dica.js` (tooltip único), `ui.js` (a "casca": tema, chip de status, turnos), `net.js` (`Atualizador`
  com ETag, pausa com a aba escondida), `dom.js` (`h`, `svg`, `segmentado`, `icone`, `quebravel`).
- Visual: papel quente + tinta + verde-limão de marca (o limão nunca é cor de partido), Archivo (largura condensada nos
  números) e DM Mono. Tokens em `:root` de `app.css` (`--papel`, `--tinta`, `--lima`, `--painel`, `--painel-borda`...),
  tema escuro por `prefers-color-scheme` e por `data-tema`. Mapa, gráfico e tabelas ficam direto sobre o papel.
- Responsivo (celular, tablet, computador), alvos de toque de 44 px, verificado com axe-core nos dois temas.
- O contorno das UFs vem de `app/static/data/mapa-ufs.json` (gerado por `python -m tools.gerar_mapa` a partir da malha
  do IBGE; só precisa rodar para mudar projeção ou detalhe).

### 3.8 Segurança do servidor

Cabeçalhos: `Content-Security-Policy` (somente a própria origem), `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`. O painel só tem rotas `GET`, sem login e sem dados pessoais. Fotos só são buscadas no
TSE para candidatos que aparecem nos arquivos (`foto_valida`), com cache negativo de 10 minutos para 404.

### 3.9 Acessos ao painel (Diagnóstico)

- `app/acessos.py` é chamado por ganchos do Flask em `create_app` (`before_request`, `after_request`, `teardown_request`);
  `/status`, `/api/v1/status` e `/healthz` não entram na conta. O resultado vai em `acessos` no `/api/v1/status` e aparece
  no quadro "Acessos ao painel" da página `/status`.
- **Páginas abertas** = respostas HTML 200 (uma visita). **Requisições** = tudo o que o navegador pede (inclui arquivos e
  fotos, como o túnel também conta). **Pessoas online (aproximado)** = aparelhos (hash de IP + navegador, com sal sorteado
  a cada partida, só em memória) que consultaram páginas ou dados nos últimos 35 s; arquivos e fotos não indicam presença.
  **Picos** (online, requisições por minuto, requisições em andamento) levam o horário de Brasília.
- Dois grupos: **pelo link público** (requisição com o cabeçalho `CF-Connecting-IP`, que o túnel da Cloudflare coloca) e
  **todos** (inclui este computador e a rede local). Nenhum IP vai para disco nem para a resposta (há teste).
- Totais e picos ficam em `data/acessos/<ambiente>.json` (gravados a cada 30 s e ao parar normalmente) e sobrevivem a
  reinícios; quem está online não. Começou a contar em 25/10/2026 às 14:50; antes disso não havia contagem.

---

## 4. Feed do TSE (fatos verificados)

- Base `https://resultados.tse.jus.br/oficial`, ciclo `ele2026`. Eleições de 2026: **6257** Presidente (2º turno
  **6258**) e **6259** Governador, Senador e deputados (2º turno **6260**); **6261** (Conselheiro Distrital) é ignorada.
  Os códigos vêm do `ele-c.json`, nunca fixos no código.
- Formatos: EA11 (configuração), EA12 (municípios), EA14/EA15 (acompanhamento), **EA20** (resultado unificado, núcleo do
  painel), EA10 (eleitos; ainda não usado). Documentação em `ref/`.
- Todos os valores são strings; percentuais com vírgula (`"45,32"`); `pvap` é a base de exibição (não recalcular).
  `dv='s'` já vem na pré-eleição com tudo zerado, então o estado vem de `and`, `s.st`, `tf`, `dt/ht`. `md`
  ("matematicamente definido") pode vir vazio mesmo no fim: a manchete também lê `eleito`/`situacao` dos candidatos.
- CDN: gzip, ETag e 304 funcionam; `max-age` varia (8 s no arquivo do Brasil, 40–58 s nos demais), então os arquivos por
  UF defasam ~1 min em relação ao nacional por desenho do TSE.
- Fotos: `fotos/br/<sqcand>.jpeg` (Presidente) e `fotos/<uf>/<sqcand>.jpeg` (demais), por eleição (inclusive no 2º turno).
- Cada `.json` tem um `.jws` (Ed25519; chave oficial em `ref/manual-verificacao-jws.pdf`); a verificação ainda **não**
  está implementada.
- `www.tse.jus.br` devolve 403 a requisições sem navegador; o feed `resultados.tse.jus.br` não.

---

## 5. API (somente leitura, `GET`)

Todas sob `/api/v1`. `?turno=1|2` aceito onde fizer sentido (outro valor: 400). Com ETag, exceto onde indicado.

| Rota | Conteúdo |
|---|---|
| `/meta` | Fase, data, turnos, turno padrão, cargos, UFs, frescor (sem ETag) |
| `/presidente` | Brasil: resultado, UFs, legenda do mapa, contagem de UFs |
| `/cargo/<governador\|senador>` | Tabela de todas as UFs do cargo |
| `/uf/<uf>` | Presidente, Governador e Senador na UF + lista dos deputados da UF |
| `/proporcional/<deputado-federal\|deputado-estadual>` | Visão nacional: vagas por agrupamento e linha por UF |
| `/proporcional/<slug>/<uf>` | Painel da UF: bancadas, destaques (20), eleitos, resultado |
| `/proporcional/<slug>/<uf>/candidatos?q=&agr=&pagina=` | Busca paginada (20; `q` até 60 caracteres; sem ETag) |
| `/historico/<presidente\|governador\|senador>/<abr>?n=3` | Evolução dos `n` (1 a 5) primeiros |
| `/municipios?uf=&q=` | Busca de município (sem ETag) |
| `/municipio/<uf>/<código>` | Disputas do município; pede ao poller para acompanhá-lo |
| `/status` | Diagnóstico do poller, do cliente HTTP e dos arquivos (sem ETag) |

Erros: 404 com `{"erro": ...}` (inclusive "pedir o 2º turno de quem não tem"), 503 com `Retry-After` quando ainda não dá
para atender.

---

## 6. Desenvolvimento

### 6.1 Testes

```powershell
.venv\Scripts\python.exe -m pytest                  # unitários e de API, sem rede (~1 min, 319 testes)
.venv\Scripts\python.exe -m pytest -m e2e           # interface no Chrome contra o simulador (~8 min, 100 testes)
.venv\Scripts\python.exe -m pytest -m live          # acessa o feed real do TSE (rede; use com parcimônia)
```

- Os e2e sobem um simulador e um painel reais em portas livres e usam o Chrome do sistema (Playwright,
  `channel="chrome"`); incluem auditoria de acessibilidade (axe-core) nos dois temas, ajuste em várias larguras de tela e
  o pior caso de siglas longas nas tabelas dos deputados. `restaurar_simulacao` volta o simulador a 50% após cada teste.
- Fixtures reais ficam em `tests/fixtures/tse/` com `MANIFEST.json` (URL, horário, tamanho, SHA-256). **Não altere os
  bytes** (Art. 267 §4 da Res. TSE 23.751/2026). Para recapturar com poucas requisições: `python -m tools.capture`
  (`--so TRECHO` recaptura só um alvo e mescla no manifesto).
- Utilitários de teste em `tests/conftest.py`: `popular_store` (carrega o Store com o simulador parado em `x`) e
  `montar_app` (app completo sem poller).
- Os testes gravam sempre em pastas temporárias, nunca na pasta `data/` do projeto; mantenha assim.

### 6.2 Simulador (ensaio)

```powershell
.venv\Scripts\python.exe -m mock.server --porta 5001 --duracao 600 --partidos-reais     # terminal 1
$env:TSE_BASE="http://127.0.0.1:5001"; $env:TSE_AMBIENTE="simulado"; $env:ESCALA_POLLING="0.25"
.venv\Scripts\python.exe run.py                                                          # terminal 2
```

- Opções: `--porta`, `--duracao` (segundos reais até 100%), `--velocidade`, `--inicio` (fração inicial, 0 a 1),
  `--partidos-reais` (candidatos fictícios com siglas reais, uma combinação diferente por UF, para ensaiar as cores).
- Controle pelo navegador (só uso local): `/__sim` (estado), `/__sim/pausar`, `/__sim/retomar`,
  `/__sim/velocidade/<x>`, `/__sim/ir/<pct>` (0 a 120), `/__sim/falha/<status>/<s>` e `/__sim/falha/limpar` (finge o TSE
  fora do ar), `/__sim/dv/<n|s>` (votos do Presidente liberados ou não).
- O painel mostra a faixa "DADOS SIMULADOS" e guarda o histórico em `data/historico/simulado/`. Para recomeçar uma
  simulação do zero, use pasta de dados nova (`DATA_DIR`), senão o histórico antigo atrapalha a curva.
- **Nunca** exponha o simulador à rede: os controles `/__sim` não têm autenticação.

### 6.3 Receitas

- **Mudar a cor de um partido:** editar `app/partidos.py` → `python -m tools.gerar_css_partidos` → rodar os testes.
- **Novo cargo ou eleição:** vem do EA11; o catálogo (`catalog.py`) já filtra por `CARGOS`/`CARGOS_GERAIS` em
  `app/tse/dominio.py`. Cargos proporcionais usam `servico.py` (seção de proporcionais) e `deputados.js`.
- **Ver como a tela fica:** simulador + Playwright com `channel="chrome"` (veja os testes e2e); cheque tema claro e
  escuro e larguras de 360 a 1440 px.
- **Convenções:** nomes e comentários em português; comentários só onde o porquê não é óbvio; sem `innerHTML` com dados;
  CSS por tokens (não coloque cor "solta"); novos textos na interface em português correto, com acentos.

### 6.4 Escala (medido em 03/10/2026 em um notebook comum: 6 núcleos e cerca de 6 GB de RAM)

- Cada requisição custa de 0,3 a 2 ms; o servidor sustenta ~400–550 req/s (~380 numa mistura realista) e ~60 visitantes
  novos por segundo. Cada pessoa com a página aberta gera ~0,15–0,2 req/s: **~1.000–1.500 pessoas simultâneas com
  folga, ~2.000 no limite**. Sobrecarregado ele não dá erro, só responde mais devagar.
- O gargalo prático é o **upload** da internet: no pico cada pessoa recebe até ~60 kbps (o gráfico de ~90 KB é o mais
  pesado); as respostas comprimem 6 a 8 vezes, mas o servidor não comprime. A primeira visita pesa ~350 KB.
- **Achado:** o waitress fecha a conexão depois de toda resposta 304 (sem `Content-Length`). A ~500 req/s isso esgotou as
  portas temporárias do Windows em ~30 s (o PC ficou ~1 minuto sem abrir conexões novas). Via túnel, vira um teto de
  algumas centenas de req/s. Corrigir é mudança de código: não fazer sem pedido.
- Armazenamento: ~300–550 bytes por ponto de histórico; a eleição inteira fica abaixo de ~100 MB em disco (histórico do
  1º turno de 2026: ~4 MB). Memória do processo: ~150–250 MB. Reiniciar recarrega o histórico em 3 a 9 s.
- Ideias para mais folga (nenhuma implementada): comprimir respostas, cache de 5–10 s na borda (túnel nomeado com
  domínio), fechar a conexão do 304 corretamente.

---

## 7. Pendências conhecidas

- Modo telão (tela cheia para projetor).
- EA10 (resultado de eleitos) e verificação das assinaturas `.jws`.
- CI no GitHub Actions; hospedagem fixa na internet (hoje roda em um computador local).
- Conselheiro Distrital de Fernando de Noronha (eleição 6261): ignorado de propósito.
- Tag `v0.4.0`, quando o dono do projeto pedir.
- O formato dos arquivos de deputados com votos foi inferido de um arquivo real da pré-eleição e da documentação do TSE;
  o histórico de 04/10 (~4 MB) mostra que o painel registrou a apuração, mas não foi revisado como as páginas de deputados
  se comportaram com votos reais. Acompanhar `/status` e as páginas em cada eleição.
