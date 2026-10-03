# Eleições ao Vivo

Painel **não oficial** de acompanhamento ao vivo da apuração das eleições brasileiras de 2026, feito em Python + Flask sobre os arquivos públicos de divulgação de resultados do TSE.

> **Aviso:** projeto independente, sem vínculo com o Tribunal Superior Eleitoral. Os números são exibidos como publicados pelo TSE, sem alteração de conteúdo (Resolução TSE nº 23.751/2026, art. 267, §4º). Para resultados oficiais, consulte sempre o TSE.

## O que já faz

- **Presidente (Brasil):** progresso da totalização, comparecimento, abstenção, brancos e nulos, ranking com foto, partido e vice, mapa de blocos das UFs mostrando quem lidera, e tabela por UF ordenável.
- **Governador e Senador:** tabela com todas as UFs e página de cada UF com o ranking completo (Senado com a linha das 2 vagas).
- **Avisos honestos:** apuração não iniciada, votação do Presidente ainda não liberada (antes das 17h de Brasília), "matematicamente definido", segundo turno, totalização final e dados desatualizados.
- Tema claro/escuro, funciona no celular, sem dependências externas no navegador (nada de CDN).
- Cores dos candidatos estáveis durante a noite: a cor segue a pessoa, não a posição no ranking.

Em desenvolvimento: municípios, deputados, gráfico de evolução e modo telão.

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

## Como funciona

```
TSE (CDN) ──GET condicional──▶ poller (servidor) ──▶ cache em memória ──▶ API Flask ──▶ navegadores
```

- Só o servidor fala com o TSE; os navegadores falam apenas com a API deste projeto, com ETag (recebem 304 enquanto nada muda).
- As eleições, os cargos e as URLs são descobertos a partir do arquivo de configuração do TSE (`ele-c.json`); o segundo turno entra sozinho quando o TSE o publicar.
- Respeita as regras de uso do TSE: no máximo 100 requisições/s por IP (o painel usa no máximo 15), consulta periódica, `If-None-Match`, sem tentativas repetidas em URLs inexistentes e disjuntor global ao ver 403/429.
- A mudança de um arquivo é detectada pelo conteúdo (hash), não pelo `idg`.

## Desenvolvimento

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest                 # testes unitários e de API (sem rede)
.venv\Scripts\python.exe -m pytest -m e2e          # interface no Chrome (Playwright) contra o simulador
```

Os testes usam arquivos reais do TSE capturados antes da eleição (`tests/fixtures/`, sem alteração) e dados sintéticos. Para recapturar os fixtures com poucas requisições: `python -m tools.capture`.

## Fonte dos dados

- Dados: <https://resultados.tse.jus.br> (arquivos JSON; os `.jws` assinados também estão disponíveis).
- Documentação técnica usada como referência: pasta [`ref/`](ref/).

## Licença

[MIT](LICENSE).
