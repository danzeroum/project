# ADR-012 — Verificação e validação são coisas distintas, e o agente que valida nunca corrige

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-CONF-002, RISK-DERIV-001

## Contexto

Onze ADRs depois, este repositório verifica muito bem uma coisa: **o repositório real corresponde
ao que foi declarado?** Schemas, asserções, partição de etapas, invariante do código órfão,
cobertura reversa de risco — tudo responde a essa pergunta, de ângulos diferentes.

Nenhum responde a outra: **o que foi declarado ainda é verdade?** A descrição de um componente
pode ter sido escrita quando ele fazia outra coisa. Um ADR `accepted` pode continuar com todas as
asserções verdes enquanto a decisão que ele registra deixou de fazer sentido. Um risco `mitigated`
pode citar um controle que existe, tem caminho válido, e não mitiga mais nada.

Nada disso é detectável por fiscal determinístico — é leitura, não checagem. E há um segundo
problema, específico do modelo derivado/alvo: o alvo **continua evoluindo**. Um derivado ancorado
num SHA de três meses atrás pode ter todos os fiscais verdes e descrever um sistema que já mudou
por inteiro, porque nada no fingerprint de conformidade sabia da existência do alvo.

## Decisão

**1. Duas palavras, dois mecanismos.**

| | Pergunta | Quem | O que faz com um achado |
|---|---|---|---|
| **Verificação** | está conforme o declarado? | fiscais determinísticos | reprova o CI |
| **Validação** | o declarado ainda é verdade? | agente `conformance` | **propõe** |

**2. O agente nunca corrige.** Todo achado sai como `change_proposal`, `risk_entry` ou `accepted`
— e `accepted` **exige** `rationale`, porque aceitar em silêncio é como um achado morre. Um agente
que conserta o que ele mesmo julga é juiz e parte: o diff entra no repositório sem que ninguém
tenha revisado o julgamento que o originou.

**3. O fiscal não lê a prosa; cobra o frescor dela.** `check_review_currency` confere que a
revisão existe e que o `scope_fingerprint` cobre este estado. É o mesmo desenho de
`check_judgment_currency` para privacidade — fiscal determinístico não sabe julgar, mas sabe muito
bem dizer se o julgamento é velho.

**4. O fingerprint inclui o SHA de `target.lock`.** É o que faz "cobre este estado" significar
alguma coisa num derivado. O efeito colateral é intencional: **avançar o lock invalida a revisão**,
e é exatamente esse o gatilho que `/sincronizar` torna visível em vez de deixar passar.

**5. Drift vira trabalho concreto, não um número.** `--sync-diff` responde "estes seis itens
descrevem arquivos que mudaram", não "o alvo andou 40 commits". E ele **não avança o lock**:
avançá-lo é decisão declarada em change-proposal, porque decidir se um item ainda vale é
julgamento.

**6. O canal de retorno ao alvo nasce `false`.** É a única capacidade deste repositório que
escreveria num repositório de terceiro. Coerente com `decision_policy.default: deny`: escrita em
repositório que não se governa começa fechada e liga por decisão declarada.

## Consequências

- Avançar o lock passa a custar uma revisão. É o ponto: sem isso o derivado envelhece em silêncio,
  que é o modo de falha mais provável de todo este desenho.
- `governance/conformance-review.yaml` nasce com três achados `accepted` — o negócio de exemplo, a
  `area: availability` sem nenhum risco, e a cegueira do adapter TS. Registrá-los como aceitos com
  razão é o oposto de escondê-los: eles ficam legíveis, e mudar de ideia sobre qualquer um exige
  editar um arquivo protegido.
- O workflow semanal roda `schedule` e `workflow_dispatch`, e é **best-effort**: um agendamento que
  falha em silêncio não pode ser a única linha de defesa, e não é — o gate continua sendo o
  `governance.yml` a cada push.
- Custo assumido: `conformance_fingerprint` cobre dez arquivos de metadado. Editar qualquer um
  invalida a revisão, inclusive por mudança cosmética. A alternativa — escopo mais fino, por campo
  — seria mais confortável e menos honesta, porque exigiria decidir de antemão quais mudanças
  "não contam", que é precisamente o julgamento que a revisão existe para fazer.

## Fiscal

`ci/audit_conformance.py::check_review_currency` (a revisão existe e cobre este estado, incluindo
o SHA do alvo); `harness/schemas/conformance-review.schema.json` (`accepted` ⇒ `rationale`;
`not_assessed` obrigatório); `harness/schemas/harness.schema.json` (`target_feedback` declarado);
`harness/agents/conformance/AGENT.md`; `.github/workflows/conformance.yml`;
`harness/policies/conformidade-continua.md`.
