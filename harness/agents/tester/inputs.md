# tester — inputs

Lê:
- `src/**`, `tests/**` — código e testes atuais.
- `tests/qa/config.yaml` — alvo e thresholds (para `passive`).
- `tests/qa/escopo-autorizado.yaml` — escopo autorizado (obrigatório antes de `passive`).
- `harness/prompts/tester-task.md` — o template da tarefa.

Não lê variáveis `WEBQA_*` — elas não existem no ambiente do tester.
