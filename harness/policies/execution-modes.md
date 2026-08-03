# Política: modos de execução e quem pode disparar

A suíte tem quatro modos, com naturezas de risco diferentes. Tratá-los como um só é o erro de
governança mais provável nesta arquitetura.

| Modo | Rede | Autorização | `agent` | `human` | `ci` |
|---|---|---|---|---|---|
| `inventory` | não | não | ✅ | ✅ | ✅ |
| `passive` | sim | escopo declarado | ⚠️ só com alvo pré-configurado | ✅ | ✅ |
| `load` | sim | `WEBQA_LOAD_AUTHORIZED` | ❌ | ✅ | segregado |
| `active_discovery` | sim | `WEBQA_DISCOVERY_AUTHORIZED` + escopo + prova de posse | ❌ **nunca** | ✅ | segregado |

## Regra dura

Um runner-kind `agent` **nunca** dispara `load` ou `active_discovery`, independentemente do que
qualquer configuração diga. Esses modos só existem em jobs `workflow_dispatch` segregados,
disparados por pessoa, com o ambiente montado ali.

O gate desses modos é uma variável de ambiente. Um agente com permissão ampla no shell poderia
exportá-la — por isso a defesa não é de arquivo nem de markdown: é o ambiente limpo do runner
(ver `env-hygiene.md`) somado à segregação de jobs no CI.

---

Fiscalizado por: `.github/workflows/qa.yml` — `inventory`/`passive` em job automático;
`load`/`active_discovery` só em jobs `workflow_dispatch` com `environment:` de revisores.
Fiscalizado por (na suíte): `webqa/gates.py::require_discovery` (fail-closed).
Declarado em: `harness/harness.yaml` → `execution_modes`.
Falha como: modo proibido ⇒ o job simplesmente não existe para o agente/CI automático.
