# Política: toda mudança proposta é declarada antes de executada

Uma mudança — especialmente proposta por agente — declara, num artefato versionado, o que afeta, o
risco, os gates exigidos e se precisa de aval humano. É o que a harness lê para **rotear, bloquear ou
escalar** (ver `decision_policy` em `harness/harness.yaml`).

Regras:
- `capabilities_affected` / `components_affected` resolvem para IDs reais (`CAP-*`, `CMP-*`); riscos
  citados existem no registro (`RISK-*`).
- **Risco `high`/`critical` exige `human_approval_required: true`** — trava estrutural no schema, não
  convenção. Um agente não pode se auto-aprovar uma mudança de alto risco.
- `change_mode` é sempre `pull_request`: a mudança passa por revisão, nunca é aplicada direto.

Isso fecha o elo entre metadado estático (capacidades, componentes, risco) e execução: o agente não
"acha" o impacto — ele o declara, e o fiscal recusa uma declaração que não bate com o repositório.

---

Fiscalizado por: `harness/schemas/change-proposal.schema.json` (forma + risco alto ⇒ aval, via
`if/then`); `ci/validate_metadata.py::check_change_proposals` (resolução de IDs e riscos).
Declarado em: `harness/change-proposals/` (contrato em `README.md`, exemplo em `EXAMPLE-CP-001.yaml`).
Falha como: proposta com ID inexistente, risco fora do registro, ou risco alto sem aval ⇒ erro de CI.
