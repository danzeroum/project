# ADR-004 — Toda mudança proposta é declarada e validada antes de executada

- **Status:** accepted
- **Data:** 2026-08-03
- **Riscos relacionados:** RISK-CHANGE-001

## Contexto

Quando um agente pode alterar o repositório, o ponto frágil deixa de ser "o código está certo?" e passa
a ser "quem autorizou esta mudança, e ela declarou o próprio impacto?". Sem um artefato de proposta
declarado e verificável, um agente poderia aplicar uma mudança de alto risco — tocar caminho protegido,
subir dependência, alterar a régua — sem que o impacto e a necessidade de aval humano ficassem
explícitos. RISK-CHANGE-001 nomeia exatamente esse risco.

## Decisão

Toda mudança — especialmente proposta por agente — é declarada como um artefato versionado em
`harness/change-proposals/`, validado por schema e semântica antes de qualquer execução:

- Declara `capabilities_affected` / `components_affected` (que resolvem para IDs reais) e os riscos
  citados (que existem no registro).
- Declara `risk_assessment`, `required_gates` e `tests_required`.
- **Risco `high`/`critical` exige `human_approval_required: true`** — trava estrutural no schema
  (`if/then`), não convenção. Um agente não se auto-aprova uma mudança de alto risco.
- `change_mode` é sempre `pull_request`: a mudança passa por revisão, nunca é aplicada direto.

A harness lê a proposta para **rotear, bloquear ou escalar** (ver `decision_policy` em
`harness/harness.yaml`).

## Consequências

- O impacto de uma mudança é declarado pelo autor e cruzado com o repositório pelo fiscal — não é
  "achado" pelo agente em tempo de execução.
- Uma proposta que afete um ID inexistente, cite um risco fora do registro, ou declare risco alto sem
  aval é recusada no CI.
- Custa disciplina: cada mudança relevante exige um artefato de proposta. É deliberado.

## Fiscal

`harness/schemas/change-proposal.schema.json` (forma + risco alto ⇒ aval, via `if/then`);
`ci/validate_metadata.py::check_change_proposals` (resolução de IDs e riscos);
`harness/policies/change-proposals.md`.
