# conformance — outputs

**Um arquivo, e só um:** `governance/conformance-review.yaml`
(schema: `harness/schemas/conformance-review.schema.json`).

```yaml
review:
  produced_by: agent
  agent: conformance
  scope_fingerprint: "sha256:…"   # python ci/audit_conformance.py --print-fingerprint
  findings:
    - id: CONF-001
      severity: medium
      summary: "…"
      disposition: change_proposal | risk_entry | accepted
      ref: CP-0xx | RISK-…          # obrigatório de fato para change_proposal
      rationale: "…"                # obrigatório pelo schema quando accepted
  not_assessed:
    - "o que esta revisão não olhou, e por quê"
```

Nunca escreve: metadado, código, fiscal, schema, `workspace/**`, nem o repositório do alvo.

`not_assessed` não é formalidade: "sem achados" numa categoria que ninguém examinou é a forma mais
silenciosa de laudo falso, e é o mesmo requisito que `privacy-review.yaml` já carrega.
