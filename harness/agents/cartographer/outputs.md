# cartographer — outputs

| Escreve | Como |
|---|---|
| `architecture/components.yaml` | itens com `derived_from`, `source_of_truth: false` |
| `architecture/interfaces.yaml` | idem |
| `business/capabilities.yaml` | idem, com `risk_level: pending_judgment` |
| `business/requirements/backlog.yaml` | idem |
| `design/ui-surfaces.yaml` | idem |
| `harness/change-proposals/CP-*.yaml` | a proposta que embala tudo acima |

Nunca escreve: `workspace/**` (é o alvo), `ci/**`, `harness/schemas/**`, `harness/policies/**`,
`governance/risk-register.yaml` (é do agente `privacy`), nem qualquer campo de julgamento.

## Forma obrigatória de cada item

```yaml
- id: CMP-EXEMPLO
  # ... campos do schema ...
  derived_from:
    repo: owner/repo          # tem de casar project.yaml:target.repo
    sha: <40 hex>             # tem de casar target.lock:target_sha, exatamente
    path: caminho/no/alvo.py  # relativo à raiz do alvo, sem workspace/target/
    section: nome_do_simbolo  # opcional
```

`ci/validate_metadata.py::check_derived_from` reprova as três primeiras se divergirem.
