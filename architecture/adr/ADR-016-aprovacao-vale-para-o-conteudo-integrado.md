# ADR-016 — Aprovação vale para o conteúdo integrado, não para o pedido

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-022

## Contexto

O ADR-004 estabeleceu que mudança de alto risco é declarada antes de executada, e o schema da
change-proposal trava `risk: high ⇒ human_approval_required: true`. Essa trava garante uma coisa
só, e é menos do que parece: ela garante que a proposta **declare** que aval era necessário.

Ela não garante que aval houve. `human_approval_required` é um campo que o próprio autor preenche.
Nem `approved_by: "@fulano"` resolveria — um login é texto que se digita. E há um modo de falha
pior que a mentira direta, porque não exige má-fé nenhuma: dependendo da configuração de dismissal
do repositório, o estado `APPROVED` de um review **sobrevive a pushes novos**. Alguém revisa o diff
A, aprova, o autor empurra o diff B, e a API continua respondendo `APPROVED`. O aval humano vira um
carimbo que se obtém uma vez e se reusa.

## Decisão

**"Aprovado" significa "aprovado para este conteúdo".** `approved_by` carrega
`{login, review_id, pr_number, approved_at}`, e `ci/verify_approval.py` resolve o review contra a
API. Reprova se: o review não existe; não está `APPROVED`; foi submetido pelo autor do PR
(auto-aprovação com um passo a mais continua sendo auto-aprovação); o login não confere; o
`commit_id` do review não é o `head_sha` que será integrado; ou o aval e a execução citam PRs
diferentes.

**`executed_in` de proposta `high` exige merge commit.** Número de PR é ponteiro para uma conversa;
merge commit é o conteúdo. Mesma distinção do ADR-015 uma camada acima, e pela mesma razão.

**A prova é exigida quando o fato existe, nunca antes.** Uma proposta não pode declarar, dentro do
próprio PR, o merge que ainda não aconteceu nem o review que ainda não foi submetido. Por isso os
campos de prova são obrigatórios sob `status: executed`, e só sob ele: a proposta entra como
`approved` e o PR seguinte a fecha com o SHA real. Exigir a prova antes do fato produziria um campo
que ninguém consegue preencher corretamente — e que, por isso, seria preenchido com qualquer coisa,
que é exatamente o modo de falha que este ADR existe para eliminar.

**Fraude e indeterminação são estados distintos** (princípio (h) do plano). Aprovação forjada
reprova com código de violação, exit 1. Execução sem credencial produz `approval_unverifiable`,
exit 3 — código próprio, para que o CI possa distinguir os dois sem ler mensagem de texto. Colapsá-
los tornaria "estou sem token" e "alguém forjou um aval" indistinguíveis, e a leitura barata
venceria: *deve ser o token*.

**Nada é retroativo.** Os campos de ciclo existem a partir de `schema_version: "1.1"`. As propostas
1.0 continuam válidas como estão. Retroagir exigiria reescrever registro histórico, e registro que
se reescreve para satisfazer fiscal novo deixa de ser registro.

## Consequências

O aval humano deixa de ser declaração e passa a ser fato resolvível. O custo é uma chamada de API
por proposta `high` executada, só no CI e só quando há credencial — e um passo a mais no processo:
fechar a proposta depois do merge.

Esse passo a mais é deliberado. Ele é o preço de não ter um campo autorreferente, e paga-se uma vez
por proposta de alto risco.

## Fiscal

`ci/audit_governance.py::check_cp_lifecycle` cobra a coerência que não depende de rede;
`ci/verify_approval.py::verify_approval` resolve o review contra a API. As asserções `ADR-016-A*`
provam que as duas peças continuam existindo, que o schema mantém as travas, e que o verificador
continua sem I/O no núcleo.
