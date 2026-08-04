# ADR-007 — Análise de LGPD sempre ligada, em dois níveis com fronteira explícita

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-PRIV-001, RISK-PRIV-002

## Contexto

Até aqui, a única menção a privacidade neste repositório era um bloco em `project.yaml`:

```yaml
classification:
  data_classification: "to-be-defined"
  lgpd_relevance: "to-be-assessed"
```

Texto livre, num bloco **opcional** no schema. Nenhum fiscal conseguia reprovar aquilo, então a
pendência podia durar para sempre sem nunca aparecer como falha — a crítica central do README
("markdown que não morde") aplicada ao próprio repositório, no único lugar onde o custo de errar
recai sobre terceiros, não sobre o time.

O erro tentador é o oposto: escrever um "fiscal de LGPD" que finge julgar. Um script que declara
uma base legal adequada, ou que trata "nenhum termo suspeito encontrado" como conformidade, vende
falso negativo como garantia — e é pior que não ter fiscal nenhum, porque produz confiança.

## Decisão

A análise de privacidade roda **a cada push, sobre o projeto inteiro**, em dois níveis com
fronteira explícita:

> **O fiscal determinístico não julga legalidade. Ele garante que o julgamento existe, é do tipo
> certo, e cobre exatamente este estado do repositório.**

**Nível 1 — determinístico (`ci/audit_lgpd.py`).** Registro das operações (Art. 37) em
`governance/data-inventory.yaml`; varredura de tratamento-sombra sobre a superfície declarada em
`harness/stages.yaml`; coerência entre o papel declarado em `project.yaml` e o inventário;
direitos do titular com endpoint (Art. 18); e frescor do julgamento (Art. 38).

**Nível 2 — julgamento (skill `/revisao-lgpd`, agente `privacy`).** Adequação da base legal à
finalidade, proporcionalidade da retenção, minimização de DTO, transferência internacional,
resposta a incidente, severidade — e se um campo que a heurística não sinalizou é ainda assim
dado pessoal. Produto em `governance/ripd.md` (prosa) e `governance/privacy-review.yaml`
(registro tipado).

**Duas travas são estruturais, não runtime.** Dado `sensivel` não admite `legitimo_interesse`
nem `protecao_credito` (Art. 11): o `then` do `if/then` restringe o enum. Papel de
controlador/operador exige `dpo_contact` (Art. 41). A violação não pode ser escrita, então não
precisa ser detectada — ADR-002 aplicado literalmente.

**Frescor por fingerprint de conteúdo, nunca por data nem `git log`.** `actions/checkout@v4`
clona com `fetch-depth: 1`: histórico não existe no CI, e data tornaria o resultado
irreprodutível. O escopo é proporcional — inventário, bloco `classification`, `tests/qa/config.yaml`
e arquivos com achado de PII. Refatorar precificação não reabre o julgamento; introduzir um campo
de CPF reabre.

**O tipo de julgamento é derivado, não escolhido.** Inventário vazio ⇒ Parecer de
Proporcionalidade (4 seções). Primeiro campo inventariado ⇒ RIPD completo (8 seções), mais
`dpo_contact`, mais os quatro direitos com endpoint, mais fingerprint novo. Três travas disparam
juntas.

## Consequências

- O projeto de exemplo sai verde hoje com um parecer enxuto e honesto — não porque ninguém olhou,
  mas porque olhou e o sistema não trata dado de titular.
- Um consumidor da carcaça que adicione PII encontra o gate no primeiro push, não na auditoria.
- O que a heurística não alcança fica registrado como asserção `manual` e em
  `privacy-review.yaml:not_assessed`, em vez de virar silêncio.
- Custo: toda mudança no escopo proporcional exige refazer o julgamento. É o ponto.
- Fronteira de longo prazo: checks profundos de LGPD pertencem à suíte externa (que já expõe o
  marcador `lgpd`) — régua fora, comparável entre projetos. `ci/audit_lgpd.py` fica com o que só
  o consumidor sabe: inventário, bases legais, retenção, frescor.

## Fiscal

`ci/audit_lgpd.py`; `harness/schemas/data-inventory.schema.json` (Art. 11 e Art. 41 como trava
`if/then`); `harness/schemas/privacy-review.schema.json`; `harness/schemas/project.schema.json`
(`classification` obrigatório, com enums); `harness/policies/lgpd.md`;
`harness/agents/privacy/AGENT.md` e `harness/prompts/lgpd-task.md` (o nível de julgamento);
`.github/workflows/governance.yml`.
