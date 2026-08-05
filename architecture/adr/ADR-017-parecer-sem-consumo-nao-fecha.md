# ADR-017 — Parecer sem consumo não fecha

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-023

## Contexto

Este repositório produz dois pareceres: `governance/conformance-review.yaml` (o julgamento de que
o metadado ainda descreve o sistema) e `governance/privacy-review.yaml` (o julgamento de LGPD).
Ambos existem porque um fiscal determinístico não julga se uma descrição ainda condiz com a
realidade — ele confere que alguém julgou, e que o julgamento cobre o estado atual.

O que faltava é o outro lado. Um achado de conformidade declara `disposition`
(`change_proposal | risk_entry | accepted`) e um `ref` opcional de texto livre. "Este achado virou
uma change-proposal" é, portanto, uma afirmação que ninguém confere: o `ref` pode citar uma
proposta que não existe, ou não citar nada.

**Um achado encaminhado para o vazio é indistinguível de um achado tratado** — e a diferença entre
os dois é a única coisa que o parecer produz.

## Decisão

Um achado encaminhado declara `consumed_by = {kind, ref}`, e `check_decision_chain` resolve o
destino contra o artefato **real**: a change-proposal existe como arquivo, o `RISK-*` existe no
registro, o `ADR-*` existe no índice. Destino que não resolve é achado — pela mesma lógica do
`assertion_unresolvable` do ADR-006: uma trava que não encontra o que vigia está quebrada, não
satisfeita.

O schema exige `consumed_by` quando a disposição declara encaminhamento. Em privacidade, a
exigência recai sobre issues `P0`/`P1` que seguem abertos ou mitigados: o schema já cobrava um
`RISK-*`; faltava o simétrico — um risco registrado sem trabalho declarado é um risco gerido apenas
no papel.

`accepted` continua sendo saída legítima, e continua exigindo `rationale`. Aceitar é uma decisão.
O que se recusa é o achado que sai do parecer sem **nenhuma** decisão: nem encaminhado, nem aceito,
apenas escrito.

## Sobre a forma rejeitada

A proposta original desta ideia eram **tipos lineares em runtime**: um parecer seria um valor que
precisa ser consumido exatamente uma vez, e deixá-lo cair seria erro de tipo. A forma foi rejeitada
na primeira rodada de revisão (R-02) — não há runtime aqui, e inventar um para carregar a metáfora
seria a inversão que o R-03 já recusou ao rejeitar orquestrador e RAG.

A **intenção** foi aprovada, e é o que este ADR registra: a linearidade sobrevive como declaração
resolvível em vez de tipo executável. O registro da forma rejeitada fica aqui para que ela não seja
reproposta sem enfrentar o motivo da rejeição.

## Consequências

Um parecer passa a ter fecho verificável: todo achado ou aponta para o trabalho que o consumiu, ou
carrega uma aceitação justificada. O custo é uma resolução de ID por achado encaminhado, sobre
coleções que o fiscal já tem em memória.

## Fiscal

`ci/audit_governance.py::check_decision_chain`, mais as travas `if/then` em
`harness/schemas/conformance-review.schema.json`. As asserções `ADR-017-A*` provam que ambas
continuam no lugar.
