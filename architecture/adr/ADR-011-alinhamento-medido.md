# ADR-011 — Cobertura de risco é medida na direção difícil, e `risk_level` continua sendo a única escala

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-ALIGN-001

## Contexto

`check_risk_control_coverage` já verificava que todo controle declarado aponta para algo real.
É a direção fácil, e ela é insuficiente pelo mesmo motivo que o ADR-009 descreve uma camada
abaixo: verificar que o declarado existe não diz nada sobre o que **não** foi declarado.

A prova de que a lacuna é real e não hipotética está no próprio repositório. Os riscos aqui eram
**todos sobre a harness** — WebQA, dependências, governança, acesso, privacidade. Nenhum sobre o
negócio, a arquitetura ou a disponibilidade. O enum de `area` traz `availability`, e nenhum risco o
usava. Ninguém percebeu por anos-fiscal de CI verde, porque nenhuma trava pergunta *o que ficou de
fora?*.

Três silêncios da mesma família apareceram junto: superfície de UI que não satisfaz requisito
algum, componente maduro cuja razão de existir ninguém registrou, e risco `open` sem prazo — que é
um risco aceito sem que ninguém tenha aceitado, e que dura para sempre justamente porque `open`
soa como trabalho em andamento.

## Decisão

**1. Quatro regras de cobertura reversa**, em `ci/alignment_report.py`:

| | Reprova quando | Porque |
|---|---|---|
| R1 | capacidade `high`/`critical` sem `RISK-*` que a referencie | risco reconhecido em campo e invisível na governança |
| R2 | risco `open` sem `treatment`, `owner` e `due` | aberto sem prazo é aceito sem ninguém ter aceitado |
| R3 | superfície de UI sem `satisfies` | ou o requisito sumiu, ou a tela não deveria existir |
| R4 | componente concreto sem requisito nem regra verificada | código maduro sem razão registrada |

**2. `risk_level` continua sendo a única escala.** O plano original previa um campo `criticality`
novo. Recusado: o schema de capacidades já exige `risk_level`, e duas escalas para a mesma
pergunta começam espelhadas e terminam discordando — sem que nada reprove, porque cada fiscal lê
a sua. É a deriva que este repositório existe para combater, e criá-la dentro do fiscal que
combate deriva seria particularmente ruim.

**3. As isenções herdam a mecânica que já funciona.** `risk_exemptions[]` tem `ref` e
`justification` obrigatória, e **isenção que não casa ativo algum é achado** — exatamente como
`stages.yaml:ungoverned`. Sem essa propriedade a lista viraria o lugar onde a cobertura é fingida
com uma linha.

**4. `docs/alignment.md` é derivado e protegido.** Como `docs/metadata-graph.md`: `--check` no CI,
negação de escrita no hook e em `.claude/settings.json`. Editar um artefato derivado à mão cria
uma fonte paralela que o CI contradiz — e a matriz de alinhamento é justamente onde alguém teria
a tentação de "corrigir" o número em vez do fato.

## Consequências

- O alinhamento entra como quinto passo de `ci/validate_all.py`, entre conformidade e LGPD: ele
  pressupõe metadado coerente e precede o julgamento de privacidade.
- Declarar uma capacidade como `high` passa a **custar**: ou existe risco associado, ou existe
  isenção justificada. É o efeito pretendido — hoje o campo podia ser preenchido e esquecido.
- R2 exige um campo de data, e este repositório evita datas em provenance (ADR-003). Não há
  conflito: aquilo é sobre fingerprint, que precisa ser reprodutível por conteúdo; um prazo de
  tratamento é dado de negócio. O fiscal cobra **presença**, nunca julga se a data é adequada.
- Custo assumido: R4 é a regra mais opinativa das quatro, e vai incomodar em repositórios que
  usam componentes como agrupamento puramente técnico. A saída declarada é `risk_exemptions`,
  não afrouxar a regra.

## Fiscal

`ci/alignment_report.py` (R1–R4, isenção morta, e `--check` do artefato derivado);
`harness/schemas/risk-register.schema.json` (`related`, `risk_exemptions` com `justification`,
`open` ⇒ `due`); `ci/hooks/post_edit_guard.py` e `.claude/settings.json` (escrita manual negada);
`harness/policies/alinhamento.md`; `.github/workflows/governance.yml`.
