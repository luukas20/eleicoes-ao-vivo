# Eleições ao Vivo

Painel **não oficial** de acompanhamento ao vivo da apuração das eleições brasileiras de 2026, feito em Python + Flask sobre os arquivos públicos de divulgação de resultados do TSE.

> **Aviso:** projeto independente, sem vínculo com o Tribunal Superior Eleitoral. Os números são exibidos como publicados pelo TSE, sem alteração de conteúdo (Resolução TSE nº 23.751/2026, art. 267, §4º). Para resultados oficiais, consulte sempre o TSE.

## O que já faz

- **Presidente (Brasil):** manchete gerada pelos números ("Fulano lidera com 44,40%"), duelo dos dois primeiros com foto, faixa de participação nos votos válidos (com a marca dos 50%), progresso da totalização, comparecimento, abstenção, brancos e nulos, ranking completo com foto, partido e vice, **mapa do Brasil** com cada estado pintado pela cor de quem lidera (clique abre a UF; estados pequenos ganham uma etiqueta ao lado; opção de ver em blocos, com o progresso de cada UF), e tabela por UF ordenável.
- **Evolução ao longo da apuração:** gráfico de linhas com o percentual dos três primeiros colocados, por horário ou por % das seções totalizadas, com dica ao passar o mouse, tocar ou usar as setas do teclado, e tabela equivalente. Existe para o Brasil e para cada UF.
- **Governador e Senador:** **mapa pelo partido de quem lidera** em cada UF, com a contagem de UFs por partido, tabela com todas as UFs e página de cada UF com placar e ranking completo (Senado com a linha das 2 vagas).
- **Deputados Federal, Estadual e Distrital:** uma aba por cargo na página de cada UF (no DF, o Distrital no lugar do Estadual) e duas páginas nacionais, `/deputados-federais` e `/deputados-estaduais`. Cada UF tem um **hemiciclo** com as vagas de cada partido ou federação (na cor do partido; a federação usa a cor do partido mais conhecido dela), a tabela de bancadas (votos, % dos votos válidos, vagas e o candidato mais votado), os candidatos mais votados com **busca** por nome (sem acento), número ou partido/federação e, depois da totalização final, a lista dos **eleitos** marcados pelo TSE. A visão nacional soma as bancadas das 27 UFs, pinta o mapa pelo partido ou federação mais votado de cada UF e traz uma linha por UF. Antes da totalização final as vagas são **provisórias** (como o TSE publica durante a apuração) e o painel diz isso; "eleito" só aparece quando o próprio TSE marca.
- **Diagnóstico (`/status`):** estado da conexão com o TSE, arquivos acompanhados e **acessos ao painel** (páginas abertas, pessoas online agora, picos, requisições), separando quem chegou pelo link público do restante. Aproximado e sem guardar IP; totais e picos sobrevivem a reinícios.
- **Municípios:** busca pelo nome na página de cada UF; a página do município mostra Presidente, Governador e Senador ali.
- **Avisos honestos:** apuração não iniciada, votação do Presidente ainda não liberada (antes das 17h de Brasília), "matematicamente definido", segundo turno, totalização final e dados desatualizados.
- **Responsivo:** celular, tablet e computador, com alvos de toque de 44 px; tema claro/escuro; sem dependências externas no navegador (nada de CDN, as fontes são servidas pelo próprio painel); acessibilidade verificada com axe-core.
- **Cores dos partidos:** cada candidato leva o tom do próprio partido (PT vermelho, PL azul, NOVO laranja...), em versões modernas calibradas entre si, com variante para o tema escuro. A cor não depende de votos nem de posição, então nunca muda durante a noite; quando dois partidos de cor parecida disputam o mesmo cargo, o menos conhecido recebe a variante clara/escura da própria cor.
- Prévia de link (WhatsApp, redes sociais) com imagem própria e título da aba com o andamento ("86,6% apurado").

Em desenvolvimento: modo telão.

## Para a noite da apuração

- **Ligue o painel antes da apuração começar.** O TSE só publica o estado atual; o gráfico de evolução existe porque o painel registra cada totalização que recebe (em `data/historico/`, e recarrega se reiniciar). Quem liga depois perde o começo da curva.
- **Abrir no tablet ou no celular:** rode com `HOST=0.0.0.0` (PowerShell: `$env:HOST="0.0.0.0"; .venv\Scripts\python.exe run.py`), descubra o IP do computador com `ipconfig` e abra `http://<IP>:8000` no aparelho, na mesma rede Wi-Fi. O Windows pode pedir permissão no firewall na primeira vez.
- O painel mostra "Ao vivo · atualizado há N s"; se o TSE parar de responder, ele avisa e segue mostrando o último dado recebido. Detalhes em `/status`.

## Como rodar

Requer Python 3.12+.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

Abra <http://127.0.0.1:8000>. O painel consulta o feed oficial do TSE (`resultados.tse.jus.br`) sozinho; para abrir a outros aparelhos da rede, defina `HOST=0.0.0.0`. As opções estão em [`.env.example`](.env.example). Há uma página de diagnóstico em `/status`.

### Ensaio com dados simulados

Um simulador reproduz o formato do TSE com candidatos e votos **fictícios** (sempre marcados como "SIMULADO"):

```powershell
.venv\Scripts\python.exe -m mock.server --porta 5001 --duracao 240          # terminal 1
$env:TSE_BASE="http://127.0.0.1:5001"; $env:TSE_AMBIENTE="simulado"; $env:ESCALA_POLLING="0.25"
.venv\Scripts\python.exe run.py                                              # terminal 2
```

Controle do simulador: `http://127.0.0.1:5001/__sim` (pausar, pular para N% da apuração, injetar falhas).

Para ensaiar as cores dos partidos, suba o simulador com `--partidos-reais`: os candidatos continuam fictícios (ALFA, BETA...), mas passam a ter siglas de partidos reais (PT, PL, PSD...), uma combinação diferente em cada UF.

### Colocar no ar com link público (opcional)

Para abrir o painel que roda no seu computador em qualquer rede (por exemplo, no celular com dados móveis) use um túnel
da Cloudflare. Com o painel rodando em uma janela do PowerShell, abra **outra** janela e rode:

```powershell
& "$env:LOCALAPPDATA\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

(No Prompt de Comando, o `cmd`, o comando é `"%LOCALAPPDATA%\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate`, sem o `&`.)
O endereço `https://...trycloudflare.com` aparece no terminal. **O link é público (qualquer pessoa com ele acessa), vale só
enquanto aquela janela estiver aberta e muda toda vez que o túnel reinicia**; o painel pode reiniciar sem mudar o link. O
guia completo (como baixar o `cloudflared`, conferir o arquivo, testar e resolver problemas) está no
[CLAUDE.md](CLAUDE.md), seções 2.2 e 2.7.

## Como funciona

```
TSE (CDN) ──GET condicional──▶ poller (servidor) ──▶ cache em memória ──▶ API Flask ──▶ navegadores
```

- Só o servidor fala com o TSE; os navegadores falam apenas com a API deste projeto, com ETag (recebem 304 enquanto nada muda).
- As eleições, os cargos e as URLs são descobertos a partir do arquivo de configuração do TSE (`ele-c.json`); o segundo turno entra sozinho quando o TSE o publicar.
- Respeita as regras de uso do TSE: no máximo 100 requisições/s por IP (o painel usa no máximo 15), consulta periódica, `If-None-Match`, sem tentativas repetidas em URLs inexistentes e disjuntor global ao ver 403/429.
- A mudança de um arquivo é detectada pelo conteúdo (hash), não pelo `idg`.
- Os arquivos de deputados são os maiores do feed (de ~100 KB a ~300 KB cada, 54 no total) e mudam pouco a cada minuto: ficam numa camada de consulta mais lenta (30 a 90 s) que a do Presidente, Governador e Senador. A API deles é `/api/v1/proporcional/<cargo>` (visão nacional), `/<cargo>/<uf>` (painel da UF) e `/<cargo>/<uf>/candidatos?q=&agr=&pagina=` (busca); Senador e deputados só têm 1º turno e seguem valendo quando o 2º turno começa.

## Desenvolvimento

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest                 # testes unitários e de API (sem rede)
.venv\Scripts\python.exe -m pytest -m e2e          # interface no Chrome (Playwright) contra o simulador
```

Os testes usam arquivos reais do TSE capturados antes da eleição (`tests/fixtures/`, sem alteração; inclui o Deputado Distrital do DF) e dados sintéticos. Para recapturar os fixtures com poucas requisições: `python -m tools.capture` (ou `--so Distrital` para um alvo só, mantendo os demais no manifesto).

### Cores dos partidos

A tabela está em [`app/partidos.py`](app/partidos.py): para cada partido, a cor no tema claro, no escuro e uma variante alternativa (mesma família, bem mais clara ou escura) usada só quando outro candidato da mesma disputa tem cor parecida. As regras de atribuição estão em [`app/cores.py`](app/cores.py) e a folha de estilo [`app/static/css/partidos.css`](app/static/css/partidos.css) é **gerada**:

```powershell
.venv\Scripts\python.exe -m tools.gerar_css_partidos              # depois de mexer em app/partidos.py
.venv\Scripts\python.exe -m tools.gerar_css_partidos --conferir   # só confere (os testes também conferem)
```

Os testes garantem contraste de leitura do texto sobre cada cor (4,5:1) nos dois temas, visibilidade das marcas no tema escuro, que os partidos principais (PT, PL, PSD, NOVO...) sejam bem distintos entre si e que a disputa real do Presidente de 2026 tenha 12 cores diferentes.

### O desenho do mapa

O painel não consulta o IBGE: o contorno das UFs já está em [`app/static/data/mapa-ufs.json`](app/static/data/mapa-ufs.json) (16 KB). Ele é gerado por `python -m tools.gerar_mapa`, que baixa a malha das UFs do IBGE, projeta (cônica equivalente de Albers), simplifica os contornos por arcos (a fronteira entre dois estados é simplificada uma vez só, então os vizinhos continuam encaixados) e calcula onde cabe a sigla dentro de cada estado. Só é preciso rodá-lo se quiser mudar a projeção ou o nível de detalhe.

## Fonte dos dados

- Dados: <https://resultados.tse.jus.br> (arquivos JSON; os `.jws` assinados também estão disponíveis).
- Contornos das UFs: IBGE, Malhas Territoriais (<https://servicodados.ibge.gov.br/api/docs/malhas?versao=3>), simplificados.
- Fontes: [Archivo](https://github.com/Omnibus-Type/Archivo) e [DM Mono](https://github.com/googlefonts/dm-mono), ambas sob a SIL Open Font License 1.1 (as licenças estão em `app/static/fonts/`).
- Tons das cores dos partidos: partiram das cores das marcas (referência: predefinições de cor dos partidos na Wikipédia em português) e foram recalibrados em OKLCH para uso em tela.
- Documentação técnica usada como referência: pasta [`ref/`](ref/).

## Licença

[MIT](LICENSE).
