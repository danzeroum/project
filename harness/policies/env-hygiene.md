# Política: o ambiente do agente nunca tem os gates

Este é o requisito não negociável desta arquitetura.

Os gates da suíte são variáveis de ambiente:

```
WEBQA_DISCOVERY_AUTHORIZED       descoberta read-only (Fase C, C1)
WEBQA_ACTIVE_PROBES_AUTHORIZED   sondagem com escrita (C2)
WEBQA_LOAD_AUTHORIZED            teste de carga
WEBQA_ACTIVE_PROBES_KILL         parada de emergência
```

Um agente com shell pode exportar qualquer uma delas. Nenhum arquivo de política impede isso,
porque a trava não é de arquivo.

## Requisito

O runner do agente roda com ambiente limpo, sempre:

```yaml
env_allowlist: [PATH, HOME, LANG]      # nada de WEBQA_*
env_denylist_prefix: ["WEBQA_"]
fail_on_denied_env: true               # aborta se encontrar, não apenas ignora
```

`fail_on_denied_env` importa: ignorar silenciosamente uma variável proibida esconde o erro de
configuração que o controle existe para revelar. Falhar ruidosamente converte um erro de
configuração em evento auditável.

Os modos 3 e 4 só existem em jobs separados, disparados por pessoa, com o ambiente montado ali.

## O hook precisa se achar de qualquer diretório (CP-020)

O comando do hook resolve a raiz do repositório **antes** de chamar o interpretador: prefere
`$CLAUDE_PROJECT_DIR` e, sem ela, sobe diretórios a partir do cwd até encontrar `ci/hooks`.

Não é detalhe de invocação. Com caminho relativo, a trava passava a depender do diretório de onde
o agente chama — e o cwd é a única coisa que ele inevitavelmente muda ao inspecionar o alvo que
governa. Um `cd workspace/target`, que a ingestão obriga, bastava para o hook não achar o próprio
arquivo: ele falhava fechado (correto), o `PreToolUse` recusava o comando, e o Bash — única
ferramenta capaz de devolver o cwd — ficava inutilizável. A sessão travava.

Fora de qualquer repositório a subida chega em `/` e a falha **permanece fechada**, que é o
comportamento certo: ali não há repositório para fiscalizar, e inventar uma raiz transformaria os
hooks em no-op silencioso — passariam sempre, e a camada que avisa cedo viraria verde constante.

---

Fiscalizado por: `.github/workflows/qa.yml` — o job automático define `env:` só com as variáveis
allowlisted e inclui um passo negativo que injeta `WEBQA_LEAK=1` para provar que o guard aborta.
Declarado em: `harness/harness.yaml` → `env_hygiene`.
Falha como: presença de `WEBQA_*` no job automático ⇒ falha explícita do CI (código `DENIED_ENV`).
