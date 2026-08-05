# conformance — inputs

| Lê | Para responder |
|---|---|
| `architecture/adr/*.md` e `index.yaml` | a decisão aceita ainda vale em espírito? |
| `architecture/components.yaml` | a descrição do componente ainda condiz com o código? |
| `business/capabilities.yaml`, `business/rules/` | a capacidade declarada ainda é a que o sistema entrega? |
| `governance/risk-register.yaml` | o risco `mitigated` segue mitigado pelo controle que cita? |
| `harness/state/code-inventory.json` | o que existe de fato no alvo |
| `workspace/target/**` | o código, **somente leitura** |
| `harness/reports/*.json` | o que os fiscais determinísticos já acharam (para não repetir) |
| `docs/alignment.md` | o que a cobertura reversa já apontou |

- `harness/prompts/conformance-task.md` — o template da tarefa.

Não lê: credenciais, rede, nem nada fora deste repositório e de `workspace/target/`.
