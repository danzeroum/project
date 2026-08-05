# ADR-027 — Aval humano ausente é lacuna declarada, não status inventado

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-035
**Irmão de:** ADR-020 (a camada local não equivale à externa) — mesma forma, mesma razão

## Contexto

A tarefa era fechar as CP-021 a CP-034: mover cada uma de `approved` para `executed` com
`approved_by` resolvível contra um review humano real. Seria a estreia do `ci/verify_approval.py`
em produção.

Ela parou num fato:

```
$ list_repository_collaborators danzeroum/project
danzeroum (admin)                 ← único colaborador
$ pull_request_read #31 / #45
"user": {"login": "danzeroum"}    ← autor de todos os PRs da série
```

**Há uma pessoa só, e ela é a autora de todas as propostas e de todos os PRs que as integraram.**

A Fraude 3 do `verify_approval` recusa exatamente isso — *"o aprovador é o autor do PR;
auto-aprovação com um passo a mais continua sendo auto-aprovação"*. O GitHub também recusa, mas o
que importa é que **o fiscal recusaria mesmo que a API deixasse**.

### O caminho alternativo também não passa

Registrado porque alguém vai propô-lo de novo. Apontar o aval para um PR de fechamento consolidado,
mantendo `executed_in` no PR original, é recusado pela **Fraude 5** (*"o aval precisa ser DESTE
merge"*). E o PR de fechamento não consegue se auto-aprovar: escrever o `review_id` exige um push, o
push move o head, e a **Fraude 4** passa a ver uma aprovação anterior ao último push.

É a mesma autorreferência que o manifesto de release resolveu declarando o pai. Aqui ela **não tem
solução**, porque o que falta não é uma referência — é uma pessoa.

## Decisão

**Nada é forjado e nada é afrouxado.** As doze CPs fecháveis — CP-022, CP-023 e CP-025 a CP-034 —
permanecem `approved`, que é o estado **verdadeiro**: integradas, com aval declarado como
*necessário* e nunca prestado.

A lacuna ganha registro próprio: **`RISK-CHANGE-002`**, `open`, `treatment: accept`, com `due`. O
schema já exige `due` de risco `open`, então a data não é convenção — é trava. Princípio (g), o
mesmo que datou o `RISK-EXT-001`.

A data é **a mesma** do `RISK-EXT-001` (`2026-11-03`), de propósito: as duas lacunas fazem a mesma
pergunta — *existe, fora deste repositório, uma autoridade que não seja quem é fiscalizado?* —
e revisá-las juntas evita que a segunda seja esquecida por ter calendário próprio.

### Duas CPs não entram na conta, por razões estruturais

| CP | Por quê |
|---|---|
| **CP-021** | é `schema_version: "1.0"` e não tem campo `status`. Os campos de ciclo existem a partir de 1.1, e a CP-022 declarou a **não-retroatividade como parte da decisão**. Promovê-la é reescrever registro histórico. |
| **CP-024** | é `deferred` e continua. Sua camada externa não foi implementada, o `RISK-EXT-001` segue aberto, e o eixo de tags reportou a lacuna na publicação da v1.0.0. Marcá-la `executed` seria falso. |

## O que impede isto de virar permanência silenciosa

Três travas, e nenhuma é nova:

1. o **schema** recusa risco `open` sem `due`;
2. o **`verify_approval` continua rodando no CI** — no dia em que alguém marcar uma CP `executed`, o
   aval é resolvido contra a API, não contra a boa-fé de quem escreveu o YAML;
3. uma **asserção prova que a Fraude 3 continua no código**.

A terceira é a que importa mais, e vale dizer por quê. Quando o fechamento incomodar — e ele vai
incomodar, porque doze propostas `approved` parecem trabalho inacabado — a tentação não será
conseguir o revisor que falta. Será apagar a checagem que o exige.

> **Afrouxar um fiscal para fazer o CI passar é a terceira opção, e é a errada.**

## O que destrava

Uma segunda identidade com direito de review. **Nenhuma linha de código muda**: o caminho direto
passa sozinho — review em cada PR mergeado, `executed_in` e `approved_by` citando o mesmo PR — e a
Fraude 4 fica satisfeita de graça, porque o head de um PR mergeado está congelado e o `commit_id` do
review é esse head.

Falta confirmar ao vivo que a API aceita review `APPROVED` em PR já mergeado. É o primeiro teste do
dia em que houver um segundo revisor, e é barato.

## Consequências

`approved` deixa de ser um estado de espera indefinida e passa a ser um estado **com prazo e dono**.

O repositório continua verde e continua dizendo a verdade sobre si mesmo — que é a única coisa que
esta harness tem para oferecer. Doze propostas visivelmente não fechadas, com o motivo escrito, valem
mais que doze `executed` cujo aval ninguém prestou.

## Fiscal

`ci/verify_approval.py::verify_approval` (Fraude 3), `harness/schemas/risk-register.schema.json`
(`open` exige `due`), `.github/workflows/governance.yml`. As asserções `ADR-027-A*` provam que o
risco existe com data, que o fiscal continua no CI e que a checagem de auto-aprovação não foi
removida.
