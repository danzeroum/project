# reviewer — inputs

Lê:
- diff do PR / mudanças propostas.
- `src/**`, `tests/**` — para avaliar cobertura e riscos.
- `harness/reports/**` — laudos e inventário já produzidos.
- `harness/prompts/review-task.md` — o template da tarefa.

O inventário que dispara (`inventory`) lê o código por AST, sem importar módulo e sem rede.
