# WEBQA_CONSUMER_CONTRACT

`contract_version: 1.0`

Contrato de interface entre um **projeto consumidor** (este repositório) e a **WebQA Suite** (o
padrão externo, `danzeroum/qa-suite`). Ele fixa o que o consumidor pode declarar, como a harness
invoca a suíte, e como laudos de projetos diferentes podem — ou não — ser comparados.

Este documento é normativo. Onde diverge da suíte instalada, a **versão exata declarada em
`requirements-qa.txt` vence**, e a divergência é um erro de configuração, não uma negociação.

O `contract_version` versiona a **forma** deste contrato (layout aceito, schemas, modos, códigos de
erro). Mudança de layout — por exemplo mover `tests/qa/` para `qa/` na raiz — é uma migração de
contrato: sobe o `contract_version` e documenta o mapa v1→v2. Enquanto o contrato é `1.0`, o layout
canônico é `tests/qa/`.

---

## 1. Layout aceito do projeto consumidor

O padrão aceita um consumidor com esta forma. Arquivos declarativos são obrigatórios; código de
verificação é proibido.

```
<consumidor>/
  src/                          código do negócio (a suíte LÊ, nunca edita)
  tests/
    unit/  integration/  e2e/   testes do projeto (entrada do inventário)
    qa/
      config.yaml               OBRIGATÓRIO — alvo + thresholds
      escopo-autorizado.yaml    obrigatório se usar modo passive/active_discovery
      campanha.yaml             opcional — quais modos rodar
  requirements-qa.txt           OBRIGATÓRIO — pin exato do padrão (== só)
  harness/                      plano de controle (ver §4)
  .github/workflows/qa.yml      invocação da suíte
```

**Proibido no consumidor** (a harness deve tratar como somente-leitura e o CI deve recusar):
`webqa/`, `checks/`, `data/caminhos-sensiveis.yaml`, `pytest.ini` de dimensões da suíte, ou
qualquer cópia editável do motor. O consumidor contribui **configuração e autorização, nunca
código de verificação.**

---

## 2. Schema de `tests/qa/config.yaml`

```yaml
standard_version: "1.0.0"        # string; DEVE ser igual ao pin em requirements-qa.txt
target:
  base_url: "https://example.invalid"   # URI do alvo publicado
  environment: staging                   # staging | production | preview
thresholds:
  max_high: 0                    # inteiro >= 0; máximo de achados severidade alta tolerados
  max_medium: 5                  # inteiro >= 0
active_gates: []                 # lista de gates que o consumidor autoriza explicitamente
```

Regras:
- `standard_version` **deve** casar exatamente com o pin de `requirements-qa.txt`. Divergência é
  erro de configuração.
- `target.base_url` só é usado por modos de rede (passive, load, active_discovery). O inventário o
  ignora.

---

## 3. Schema de `tests/qa/escopo-autorizado.yaml`

Obrigatório para qualquer modo que toca a rede.

```yaml
authorized: true                 # booleano; false ⇒ modos de rede são recusados
scope:
  hosts: ["example.invalid"]     # hosts em escopo, comparação de origem EXATA
  paths_in_scope: ["/api/*"]     # caminhos autorizados
  paths_excluded: ["/admin/*"]   # caminhos explicitamente fora
proof_of_possession:             # obrigatório e não-vazio para active_discovery
  method: dns-txt                # dns-txt | file | header
  reference: "not-configured"    # referência verificável da prova
authorization_expires: "2026-12-31"   # data ISO; expirado ⇒ recusa
```

A suíte compara origem **exata** — um host fora da lista nunca é tocado, mesmo que resolva para o
mesmo IP. `active_discovery` exige `proof_of_possession.reference` não-vazio e verificável.

---

## 4. Os quatro modos de execução e a matriz runner-kind

| Modo | O que faz | Rede | Autorização | `agent` | `human` | `ci` |
|---|---|---|---|---|---|---|
| `inventory` | lê o código, cataloga testes (Trabalho B) | não | não | ✅ | ✅ | ✅ |
| `passive` | roda `checks/` contra o alvo (GET normais) | sim | escopo declarado | ⚠️ só com alvo pré-configurado | ✅ | ✅ |
| `load` | rajada de requisições | sim | `WEBQA_LOAD_AUTHORIZED` | ❌ | ✅ | job segregado |
| `active_discovery` | pede recursos não linkados (Fase C) | sim | `WEBQA_DISCOVERY_AUTHORIZED` + escopo + prova de posse | ❌ **nunca** | ✅ | job segregado |

Regra dura, independente de configuração: um runner-kind `agent` **nunca** dispara `load` ou
`active_discovery`. Esses modos só existem em jobs `workflow_dispatch` segregados, disparados por
pessoa (ver `.github/workflows/qa.yml`).

### Higiene de ambiente (a trava que morde)

O runner de qualquer agente roda com ambiente limpo:

```yaml
env_allowlist: [PATH, HOME, LANG]
env_denylist_prefix: ["WEBQA_"]
fail_on_denied_env: true         # aborta se encontrar, não apenas ignora
```

`fail_on_denied_env` importa: ignorar silenciosamente uma variável proibida esconde o erro de
configuração que o controle existe para revelar. Um agente com shell não deve ter como receber,
preservar ou injetar `WEBQA_*`.

---

## 5. Contrato JSON do laudo

Todo artefato produzido carrega a procedência do padrão. Schema completo em
`harness/schemas/report.schema.json`; o bloco de procedência em
`harness/schemas/provenance.schema.json`.

```json
{
  "schema_version": "1.0",
  "standard": {
    "name": "webqa-suite",
    "version": "1.0.0",
    "commit": "0000000",
    "sensitive_paths_hash": "sha256:..."
  },
  "consumer_project": {
    "repository": "danzeroum/project",
    "commit": "a1b2c3d"
  },
  "execution": {
    "run_id": "2026-08-03T13-34-00Z",
    "mode": "inventory",
    "network_used": false,
    "active_gates": [],
    "runner_kind": "ci"
  },
  "result": "ok",
  "findings": []
}
```

- `schema_version` — evolução do formato.
- `run_id` — cruza laudo, logs e decisão do agente.
- `network_used` — evidência objetiva do modo.
- `runner_kind` — distingue execução por `agent`, `ci` e `human`.
- `sensitive_paths_hash` — hash SHA-256 da lista curada da suíte. Fecha o buraco de §3 do
  documento: dois laudos com a mesma versão do padrão e hashes diferentes ⇒ alguém editou a lista.
- `result` — `ok | findings | suite_not_installed | error`.

---

## 6. Códigos de erro da CLI da suíte

A CLI `webqa` sai com códigos estáveis (exit code, nunca traceback). A harness/CI trata falha de
configuração como evento operacional, não como crash.

| Código | Nome | Significado |
|---|---|---|
| 0 | `OK` | run concluído, veredito produzido |
| 2 | `USAGE` | uso incorreto da CLI / argumentos inválidos |
| 10 | `DENIED_ENV` | variável denylisted presente com `fail_on_denied_env` ⇒ abortado |
| 11 | `MODE_FORBIDDEN` | este runner-kind não pode disparar este modo (ex.: agent→load) |
| 12 | `SCOPE_MISSING` | modo de rede sem escopo autorizado / prova de posse |
| 20 | `SUITE_UNINSTALLED` | pacote `webqa-suite` não disponível (degradação tolerante) |
| 21 | `SUITE_ERROR` | a suíte rodou e retornou erro |
| 30 | `PROVENANCE_INVALID` | laudo sem bloco de procedência válido |
| 31 | `NOT_COMPARABLE` | agregação recusou: réguas incompatíveis |
| 40 | `CONFIG_INVALID` | `harness.yaml`/`config.yaml` falhou schema ou regra de pin |

---

## 7. Regras de compatibilidade de versão

Comparar laudos entre projetos só é honesto se todos foram produzidos pela **mesma régua**. A
agregação computa uma _fingerprint_ de cada laudo:

```
fingerprint = (standard.name, standard.version, standard.commit,
               standard.sensitive_paths_hash, schema_version)
```

- Se as fingerprints de dois laudos diferem em qualquer campo ⇒ resultado **`not_comparable`**
  (código 31). "Não comparável" é um resultado válido, muito melhor que um dashboard aparentemente
  preciso e enganoso.
- **Projetos declaram versão exata** (`==`), nunca faixa. A superfície do que a suíte procura é
  dado de segurança; não deve mudar sozinha entre dois runs.
- **Subir de versão é decisão versionada**, num PR do projeto, com o laudo anterior e o novo lado
  a lado. A harness pode _propor_ a subida; nunca executá-la sozinha.
