# harness/change-proposals — a ponte para execução agentic

Cada mudança proposta (por agente, humano ou CI) é declarada aqui como um artefato versionado, antes
de ser executada. É o que a harness lê para **rotear, bloquear ou escalar para humano** — o elo entre
os metadados estáticos (capacidades, componentes, risco) e a ação.

Contrato: `../schemas/change-proposal.schema.json`. Fiscal: `ci/validate_metadata.py`.

Uma proposta declara:
- `capabilities_affected` / `components_affected` — que devem resolver para IDs reais (`CAP-*`, `CMP-*`).
- `risk_assessment` — nível + racional; `risks` opcionais apontam para `RISK-*` do registro.
- `required_gates` — quais verificações a mudança exige (inventário, passivo, testes, etc.).
- `human_approval_required` — **obrigatoriamente `true` quando o risco é high/critical** (trava
  estrutural no schema, não convenção).

O fiscal recusa uma proposta que afete um ID inexistente, que cite um risco fora do registro, ou que
declare risco alto sem aval humano. `EXAMPLE-CP-001.yaml` é um exemplo válido de referência.
