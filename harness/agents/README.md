# harness/agents — contratos dos agentes

Cada subpasta é um agente que a harness pode invocar sobre este projeto. Um contrato tem três
arquivos:

- `AGENT.md` — identidade, quais modos pode disparar, o que nunca pode, higiene de ambiente.
- `inputs.md` — exatamente o que o agente lê.
- `outputs.md` — exatamente o que o agente escreve.

Regra transversal a todos: o runner-kind de qualquer agente é `agent`, e um `agent` **nunca**
dispara `load` ou `active_discovery` (ver `../policies/execution-modes.md`). O ambiente do runner
é limpo — variável `WEBQA_*` presente aborta a execução (ver `../policies/env-hygiene.md`).

| Agente | Pode disparar | Escreve |
|---|---|---|
| `developer` | nenhum modo da suíte | `src/`, `tests/unit/` |
| `reviewer` | `inventory` | comentários de revisão, `harness/reports/` |
| `tester` | `inventory`, `passive` (só com alvo pré-configurado) | `tests/`, `harness/reports/` |
| `documenter` | nenhum modo da suíte | `docs/`, `README`, laudos legíveis |
| `privacy` | `inventory` | `governance/ripd.md`, `governance/privacy-review.yaml`, `harness/reports/` |
