# ADR-001 — Consumir a WebQA Suite como padrão externo, nunca copiado

- **Status:** accepted
- **Data:** 2026-08-03
- **Riscos relacionados:** RISK-WEBQA-001

## Contexto

A WebQA Suite fornece o motor de verificação, os checks de qualidade e a lista curada de caminhos
sensíveis. Se cada projeto consumidor tiver uma cópia editável desse código, alguém pode remover uma
linha da lista curada que "dava trabalho"; a suíte para de procurar aquilo naquele projeto; e o laudo
continua dizendo "nenhum achado", sem erro nem aviso — indistinguível de um projeto seguro.

Uma trava que o vigiado pode desligar em silêncio não é uma trava.

## Decisão

O projeto **declara** a WebQA Suite como dependência versionada (`requirements-qa.txt`, pin exato
`==`) e a consome pela CLI. `webqa/`, `checks/` e `data/caminhos-sensiveis.yaml` **nunca** existem
neste repositório. O consumidor contribui apenas configuração e autorização.

## Consequências

- Comparabilidade entre projetos preservada: todos usam a mesma régua, versionada.
- Atualização é uma subida de pin revisada, não um merge de código.
- A harness trata caminhos do padrão como somente-leitura, categoricamente.
- Custo: o consumidor não pode adicionar um check local; verificações novas são propostas ao padrão.

## Fiscal

`.github/workflows/qa.yml` (recusa `webqa/`, `checks/`, `data/` versionados) e
`harness/policies/webqa.md`.
