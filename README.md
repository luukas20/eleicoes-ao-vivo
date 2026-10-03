# Eleições ao Vivo

Painel **não oficial** de acompanhamento ao vivo da apuração das eleições brasileiras de 2026, feito em Python + Flask sobre os arquivos públicos de divulgação de resultados do TSE.

> **Aviso:** projeto independente, sem vínculo com o Tribunal Superior Eleitoral. Os números são exibidos como publicados pelo TSE, sem alteração de conteúdo (Resolução TSE nº 23.751/2026, art. 267, §4º). Para resultados oficiais, consulte sempre o TSE.

**Status:** em construção. O núcleo de acesso ao feed do TSE (montagem de URLs, cliente HTTP com limite de taxa e interpretação dos arquivos) está pronto e testado; o painel web ainda está em desenvolvimento, então ainda não há aplicação para rodar.

## Desenvolvimento

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

Os testes usam arquivos reais do TSE capturados antes da eleição (`tests/fixtures/`, sem alteração) e dados sintéticos; nenhum teste acessa a rede por padrão (`pytest -m live` reservado para testes contra o feed real). Para recapturar os fixtures com poucas requisições: `python -m tools.capture`.

## Como vai funcionar

```
TSE (CDN) ──GET condicional──▶ poller (servidor) ──▶ cache em memória ──▶ API Flask ──▶ navegadores
```

- Só o servidor fala com o TSE, de forma periódica e dentro dos limites de uso; os navegadores falam apenas com a API deste projeto.
- Arquivos consumidos: configuração de eleições (EA11) e municípios (EA12), resultado unificado (EA20), acompanhamento Brasil/UF (EA14/EA15) e eleitos (EA10). Arquivos de urna (BU/RDV/log) estão fora do escopo.
- Eleições 2026: Presidente, Governador, Senador e Deputados. Os códigos de eleição são descobertos a partir do arquivo de configuração do TSE, não ficam fixos no código.

## Fonte dos dados e regras de uso do TSE

- Dados: <https://resultados.tse.jus.br> (arquivos JSON e JWS assinados).
- Documentação técnica usada como referência: pasta [`ref/`](ref/).
- Regras que o projeto respeita: no máximo 100 requisições por segundo por IP (o projeto usa um limite bem menor), consulta periódica dos arquivos, sem listagem de diretórios e sem tentativas repetidas em URLs inexistentes.

## Licença

[MIT](LICENSE).
