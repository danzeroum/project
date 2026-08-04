# privacy — inputs

Lê:
- `governance/data-inventory.yaml` — o registro das operações declarado (Art. 37).
- `governance/privacy-review.yaml` e `governance/ripd.md` — o julgamento anterior, para saber o
  que mudou desde então.
- `harness/stages.yaml` — a superfície do projeto e a lente de privacidade de cada etapa
  (`privacy_lens.question`). É daqui que sai o escopo do julgamento, não de palpite.
- `project.yaml` — papel declarado, criticidade, exposição, retenção de evidência.
- `src/**`, `tests/**`, `business/**`, `architecture/**`, `design/**`, `tests/qa/**` — o material
  auditado.
- `harness/reports/lgpd-audit.json` — o laudo determinístico mais recente: os achados que a
  máquina já encontrou, para não repeti-los como se fossem descoberta do julgamento.
- `harness/prompts/lgpd-task.md` — o template da tarefa.

O inventário que dispara (`inventory`) lê o código por AST, sem importar módulo e sem rede.
