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

---

Fiscalizado por: `.github/workflows/qa.yml` — o job automático define `env:` só com as variáveis
allowlisted e inclui um passo negativo que injeta `WEBQA_LEAK=1` para provar que o guard aborta.
Declarado em: `harness/harness.yaml` → `env_hygiene`.
Falha como: presença de `WEBQA_*` no job automático ⇒ falha explícita do CI (código `DENIED_ENV`).
