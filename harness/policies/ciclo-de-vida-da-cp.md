# Ciclo de vida da change-proposal

O ADR-004 diz que mudança é declarada antes de executada. Esta política diz o que acontece
**depois** da declaração — e é a metade que faltava.

## Os estados

| Estado | Significa |
|---|---|
| `draft` | escrita, ainda em discussão |
| `approved` | revisada e aceita; entra no PR neste estado |
| `executed` | integrada; **exige** dizer onde, e quem aprovou se o risco é alto |
| `rejected` | decidida contra; fica no repositório, porque proposta rejeitada é registro |
| `superseded` | substituída por outra; a nova cita a antiga |
| `deferred` | depende de condição externa e **não conta como implementada** |

`deferred` é estado de primeira classe por um motivo concreto: sem ele, uma CP que espera uma
condição externa ficaria eternamente `approved`, passando por pronta.

## As regras que mordem

**`executed` exige `executed_in`.** Uma proposta executada em lugar nenhum é uma decisão sem rastro.

**`executed` + risco alto exige `approved_by` e merge commit.** Número de PR é ponteiro para uma
conversa; merge commit é o conteúdo. E `human_approval_required: true` declara que aval era
*necessário* — jamais que aval *houve*.

**O aval é resolvido, não declarado.** `ci/verify_approval.py` busca o review pela API e recusa:
review inexistente, estado diferente de `APPROVED`, aprovador igual ao autor do PR, login que não
confere, aval e execução em PRs diferentes, e — o caso que motivou o endurecimento —
**aprovação anterior ao último push**, ainda que a API a exponha como `APPROVED`.

**A prova é exigida quando o fato existe.** A proposta entra no PR como `approved`; o PR seguinte a
fecha com o SHA real do merge. Exigir dentro do próprio PR um merge que ainda não aconteceu
produziria um campo impossível de preencher corretamente — e campos assim são preenchidos com
qualquer coisa.

**Nada é retroativo.** Os campos existem a partir de `schema_version: "1.1"`. Reescrever propostas
antigas para satisfazer fiscal novo transformaria registro em rascunho.

## Quando não há a quem pedir aval

Doze propostas deste repositório (CP-022, CP-023 e CP-025 a CP-034) estão `approved` e vão continuar.
Não por descuido: **há um colaborador só, e ele é o autor de todas elas e dos PRs que as
integraram.** A Fraude 3 recusa esse aval, e recusaria mesmo que a API o permitisse.

O estado verdadeiro é `approved` — *integrada, com aval declarado como necessário e nunca prestado*.
Não existe status que descreva isso melhor, e inventar um seria trocar uma lacuna visível por um
rótulo confortável.

A lacuna vira **risco datado**: `RISK-CHANGE-002`, `open`, `due: 2026-11-03` — a mesma data do
`RISK-EXT-001`, porque as duas fazem a mesma pergunta. O schema recusa risco `open` sem `due`, então
a data é trava, não convenção (ADR-027).

**O que destrava é uma segunda pessoa, não uma emenda.** Com um revisor independente, o caminho
direto passa sem mudar uma linha: review no PR mergeado, `executed_in` e `approved_by` no mesmo PR,
e a regra do head satisfeita de graça porque o head de um PR mergeado está congelado.

## Fraude e indeterminação

Aprovação forjada → exit 1, com o código da violação. Sem credencial → `approval_unverifiable`,
exit 3. Códigos distintos porque as reações são opostas: uma exige investigação, a outra exige
credencial. Colapsá-los ensina a ler qualquer vermelho como "deve ser o token".

Fiscalizado por: `ci/audit_governance.py::check_cp_lifecycle`, `ci/verify_approval.py::verify_approval`, `harness/schemas/change-proposal.schema.json`
Declarado em: `harness/change-proposals/CP-022-ciclo-de-vida-da-cp.yaml`
Falha como: proposta `executed` sem prova ⇒ achado bloqueante; aval que não resolve ⇒ exit 1; sem credencial ⇒ exit 3.
