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

## O CI materializa o alvo antes de fiscalizar (CP-016)

Os workflows rodam `ci/bootstrap.py --only-workspace` **antes** dos fiscais, e só quando
`project.yaml:project.kind` é `derived`. Sem isso, a invariante do código órfão — o coração do
ADR-009 e da ingestão — nunca executava no único lugar que a doutrina chama de gate: *"o hook é
ergonomia, o CI é o gate"* era verdadeiro para o molde e falso para todo derivado que ele gera.

**Materializar e validar são passos separados, e a separação é o ponto.** Clone recusado por rede,
credencial ausente ou SHA sumido por force-push no alvo são estados do **mundo**; divergência de
metadado é estado do **repositório**. O primeiro sai `2` — "o fiscal não conseguiu fiscalizar" —,
nunca `1`. Colapsar os dois ensina a ler "governança falhou" como "provavelmente foi a rede", e a
partir daí o gate está desligado por hábito, sem ninguém ter decidido desligá-lo.

**Credencial declarada, não descoberta.** O passo usa o `GITHUB_TOKEN` do runner, que basta para
alvo público na mesma conta; alvo privado ou em outra organização exige
`secrets.TARGET_READ_TOKEN`. Está escrito no workflow porque segredo descoberto por tentativa vira
variável copiada de outro projeto, e o escopo real de um segredo copiado nunca é o pretendido. A
URL é montada de `project.yaml:target.repo` — nome de alvo não entra em `.github/` (ADR-008-A5).

---

Fiscalizado por: `.github/workflows/qa.yml` — `inventory`/`passive` em job automático;
`load`/`active_discovery` só em jobs `workflow_dispatch` com `environment:` de revisores.
Fiscalizado por (na suíte): `webqa/gates.py::require_discovery` (fail-closed).
Declarado em: `harness/harness.yaml` → `execution_modes`.
Falha como: modo proibido ⇒ o job simplesmente não existe para o agente/CI automático.
