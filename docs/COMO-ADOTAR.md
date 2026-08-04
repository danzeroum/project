# Playbook do agente — adotar um repositório sob a harness padrão

> **O caminho executável agora é `/adotar` → `/bootstrap`.** Este documento explica o *porquê* de
> cada passo e o que o agente decide; o *como* mora em `.claude/commands/adotar.md`,
> `.claude/commands/bootstrap.md` e `ci/bootstrap.py`. Por ADR-002, a página não reimplementa o
> procedimento — uma regra escrita aqui e executada ali vira duas fontes que derivam em silêncio.
>
> Mudou também **onde** os metadados moram. Não é mais no repositório recebido: o `/adotar` cria um
> **derivado** (`project-<alvo>`) que **declara** o alvo em `project.yaml:target`, ancora o commit
> exato em `target.lock` e materializa o código em `workspace/target/` (efêmero). O alvo é lido,
> nunca escrito. Ver ADR-008 e `harness/policies/adocao.md`.

Guia **genérico** para um agente de desenvolvimento que recebe um repositório do GitHub e precisa
colocá-lo sob esta harness. O agente **começa copiando a casca deste molde** (`danzeroum/project`),
**declara a régua** (`danzeroum/qa-suite`) na versão mais atual, e adapta ao domínio de negócio.

Os exemplos concretos usam **um único** domínio, apenas para ilustrar: `github.com/danzeroum/docker`
(o "Docker Cockpit", uma app web FastAPI). Em qualquer outro repositório, troque os valores de
exemplo pelos do domínio recebido.

---

## 0. Entradas do agente

| Símbolo | O que é | Exemplo (só ilustrativo) |
|---|---|---|
| `REPO_ALVO` | o projeto de negócio recebido | `github.com/danzeroum/docker` |
| `MOLDE` | a casca da harness (este repo) | `github.com/danzeroum/project` |
| `PADRÃO` | a régua de QA, versionada | `github.com/danzeroum/qa-suite` (hoje `1.0.0`) |

## 1. Invariantes que o agente NUNCA viola

Estas regras valem para todo repositório. Se um passo as feriria, o agente para e reporta.

1. **Declarar, não copiar a régua.** `webqa/`, `checks/` e `data/caminhos-sensiveis.yaml` **nunca**
   entram no `REPO_ALVO`. A régua é declarada por versão (passo 4).
2. **Versão em fonte única.** O número da régua mora só em `requirements-qa.txt`. Todo o resto
   **referencia**, nunca restata (o schema recusa restatar).
3. **Inventário antes de auditoria.** Trabalho B (ler testes, sem rede) é sempre seguro; Trabalho A
   (medir o alvo publicado) exige alvo + autorização. Comece pelo B.
4. **Segredo não se comita.** O `escopo-autorizado.yaml` real (com host e prova de posse) nunca vai
   para um repo público — é injetado como segredo no CI.
5. **Modo pesado só por humano.** `load` e `active_discovery` (sondagem ativa) só em job segregado
   `workflow_dispatch`; agente/CI automático nunca dispara.
6. **Metadado só com fiscal.** Todo YAML novo ganha schema + passo no `validate_metadata.py`, senão é
   "markdown que não morde".
7. **ADR sem asserção não é decisão fiscalizável.** Todo ADR `accepted` declara ao menos uma
   asserção executável em `architecture/adr/index.yaml` — ou uma `manual` com justificativa quando
   o que ele promete genuinamente não for verificável por máquina. O schema recusa o contrário.
8. **Etapa sem fiscal não é cobertura.** Todo arquivo do `REPO_ALVO` pertence a exatamente uma etapa
   de `harness/stages.yaml` ou a uma isenção justificada. Diretório novo exige declarar a etapa.
9. **Dado pessoal só com inventário e julgamento.** Campo com forma de PII exige entrada em
   `governance/data-inventory.yaml` **e** revisão pela skill `/revisao-lgpd`, registrada em
   `governance/privacy-review.yaml` com o `scope_fingerprint` do estado avaliado. Suprimir um
   achado é declarar a exclusão com motivo, nunca apagar termo do léxico do fiscal.

> **Migração `metadata_version` 1.0 → 1.1.** Quem copiou a casca antes desta versão tem
> `classification` como bloco opcional de texto livre em `project.yaml`. Agora ele é obrigatório e
> com enums: `data_classification` ∈ `public|internal|confidential|restricted` e `lgpd_relevance` ∈
> `none|incidental|controller|operator|controller_and_operator`. Um `"to-be-assessed"` deixa de
> passar — que é o ponto: pendência que nenhum fiscal reprova dura para sempre.

## 2. Reconhecimento do `REPO_ALVO` (o agente descobre, não presume)

Antes de copiar nada, o agente lê o repositório recebido e responde:

- **Linguagem / stack?** (ex.: Python + FastAPI) — define como os testes rodam.
- **Já tem `tests/`?** — é a entrada do inventário (Trabalho B).
- **É uma app web publicada?** Tem uma URL (produção e, de preferência, **homologação**)? — habilita o
  Trabalho A.
- **Domínios de negócio e módulos principais?** — serão as capacidades/componentes (passo 7, opcional).

> Exemplo (só docker): FastAPI em `app/`, testes em `tests/` (`test_api.py`, `test_backend.py`,
> `test_acessibilidade.py`…), servido por HTTPS. Habilita B e A.

## 3. Copiar a casca mínima do `MOLDE`

Do `MOLDE`, o agente copia **apenas a estrutura declarativa** para dentro do `REPO_ALVO`:

```
REPO_ALVO/
├── harness/                     plano de controle (harness.yaml, policies/, agents/, schemas/, prompts/)
│   └── runs/ reports/ state/    evidência (gitignored)
├── tests/qa/
│   ├── config.yaml              alvo + thresholds
│   ├── escopo-autorizado.yaml   você cria a partir do .example (só se auditar rede)
│   └── campanha.yaml            modos recorrentes
├── requirements-qa.txt          declara a régua (passo 4)
└── .github/workflows/qa.yml     CI: inventário+passivo automáticos; carga/sondagem segregados
```

**Opcional, mas recomendado depois:** a camada de governança (`ci/validate_metadata.py`,
`ci/generate_graph.py`, `.github/workflows/validate-metadata.yml`, `harness/schemas/*`, e os
metadados `project.yaml`, `business/`, `architecture/`, `governance/`, `design/`). Ela liga
capacidade → componente → teste → risco → decisão. Não é necessária para o primeiro run.

## 4. Descobrir e declarar a versão mais atual da régua

O agente lê a versão real do `PADRÃO` — a fonte é o `pyproject.toml` da suíte (ou a última tag Git):

```bash
grep -m1 '^version' qa-suite/webqa-suite/pyproject.toml   # hoje: version = "1.0.0"
```

E fixa em `requirements-qa.txt`. Como a suíte **ainda não é publicada no PyPI**, o pin aponta para o
Git na versão exata:

```
# Padrão DECLARADO, nunca copiado. Versão exata.
webqa-suite @ git+https://github.com/danzeroum/qa-suite@v1.0.0#subdirectory=webqa-suite
```

Depois, alinha o espelho: `tests/qa/config.yaml → standard_version: "1.0.0"` (o fiscal cobra que o
espelho case com o pin). **Subir de versão no futuro** é um PR próprio, com o laudo anterior e o novo
lado a lado — nunca automático.

> Quando a suíte publicar no PyPI, o pin vira `webqa-suite==1.0.0`.

## 5. Apontar para o alvo (config.yaml)

O agente preenche `config.yaml` com a URL do domínio e os limites aceitáveis. O `config.yaml` da
régua usa `target_url` + `thresholds`:

```yaml
target_url: "https://<alvo-de-homologacao>"   # ou a env WEBQA_TARGET_URL
thresholds:
  ttfb_ms: 800
  p95_ms: 1500
  a11y_critical_max: 0
  max_console_errors: 0
```

## 6. Autorizar (só para modos de rede)

A partir do exemplo da suíte, o agente prepara o escopo — **e nunca comita o arquivo real**:

```bash
cp escopo-autorizado.yaml.example tests/qa/escopo-autorizado.yaml
```
```yaml
alvos:
  - origem: "https://<host-de-homologacao>"   # origem EXATA, https
    autorizado_por: "<responsavel>"
    ambiente: "homologacao"                     # nunca 'producao' para modos com escrita
    verificacao: { tipo: "dns_txt", valor: "webqa-ownership=<hash>" }
```

## 7. Popular a camada de metadados a partir do código real

**Deixou de ser opcional.** Depois do ADR-009, todo arquivo sob `target.code_roots` pertence a
`source_paths` de exatamente um `CMP-*` ou a uma isenção justificada — e
`python ci/inventory_code.py` mostra, em qualquer linguagem, o que ainda não tem dono. Um derivado
recém-criado nasce **vermelho** por construção: ele carrega os metadados de exemplo do molde, que
não descrevem o alvo, e o código do alvo ainda não foi reivindicado. Ficar verde é o trabalho.

O agente declara, cruzando com o repositório real (o fiscal recusa se não bater):

- `business/capabilities.yaml` — capacidades (`CAP-*`) apontando para os módulos e testes que existem.
- `architecture/components.yaml` — componentes (`CMP-*`) → código, `implements` os requisitos.
- `business/requirements/backlog.yaml` — requisitos (`REQ-*`), `validated_by` os testes reais.
- `governance/risk-register.yaml`, `architecture/adr/`, `design/ui-surfaces.yaml` — risco, decisão, UI.

> Exemplo (só docker): `CAP-COCKPIT` → `app/routers/*`, `CMP-API` → `app/app.py` (`implements`
> `REQ-…`), `validated_by: [tests/test_api.py]`, etc. O `generate_graph.py` desenha o mapa.

## 8. Rodar — na ordem de risco

Hoje a régua **não tem CLI instalável** (v1.0.0): roda por `pytest -m <marcador>`, `make` e um
container Docker. Marcadores disponíveis: `backend, frontend, ux, functional, acceptance, lgpd,
seguranca, browser, load`.

```bash
# Trabalho B — INVENTÁRIO (sempre; sem rede, sem autorização): os testes do próprio projeto
pytest -q

# Trabalho A — PASSIVO (com alvo + escopo): a régua mede o alvo publicado, GET normais
pip install "webqa-suite @ git+https://github.com/danzeroum/qa-suite@v1.0.0#subdirectory=webqa-suite"
WEBQA_TARGET_URL="https://<homologacao>" pytest -m "backend or frontend or ux or seguranca or lgpd" -m "not load and not browser"

# Métricas de renderização (FCP/LCP/CLS) — precisam de Chromium real: via container da suíte
docker compose -f qa-suite/docker/compose.yml run --rm campanha

# Governança do REPO_ALVO (se adotou o passo 7)
python ci/validate_metadata.py && python ci/generate_graph.py --check
```

## 9. Modos pesados — só por pessoa

`load` (carga) e `active_discovery` (Fase C — procura recursos não linkados) **nunca** por agente. Eles
existem só como job `workflow_dispatch` no `qa.yml`, com o gate montado ali:
`WEBQA_LOAD_AUTHORIZED`, `WEBQA_DISCOVERY_AUTHORIZED` + escopo + prova de posse. O ambiente do agente
é limpo (denylist `WEBQA_*`, `fail_on_denied_env: true`).

## 10. Entregar

O agente abre um **PR no `REPO_ALVO`** com a casca preenchida (passos 3–6, opcionalmente 7). Todo
laudo carimba a **procedência**: versão da régua, commit e hash da lista curada — o que torna a
comparação (hoje × amanhã, ou entre projetos) honesta. Se a régua mudou, o sistema diz "não
comparável" em vez de mentir.

---

## Checklist de "pronto"

- [ ] `webqa/`, `checks/`, `data/caminhos-sensiveis.yaml` **ausentes** no `REPO_ALVO`.
- [ ] `requirements-qa.txt` pina a régua na versão exata descoberta; `standard_version` casa.
- [ ] `config.yaml` aponta para um alvo de **homologação**; thresholds do domínio preenchidos.
- [ ] `escopo-autorizado.yaml` real **não** comitado (só o `.example`); ou ausente se não auditar rede.
- [ ] Inventário (`pytest -q`) roda; passivo roda contra o alvo autorizado.
- [ ] `load`/`active_discovery` só em `workflow_dispatch`; ambiente do agente sem `WEBQA_*`.
- [ ] (Se adotou governança) `validate_metadata.py` verde e diagrama `--check` em dia.
- [ ] PR aberto no `REPO_ALVO` com laudo carimbando a procedência.

## Red flags (o agente para e pergunta)

- Alguém pede para copiar a régua "para simplificar" → recusar (invariante 1).
- Pedido de rodar carga/sondagem em **produção** por automação → recusar; exige humano + homologação.
- Duas cópias do número da versão → violação da fonte única (invariante 2).
- Metadado novo sem schema/fiscal → não entra (invariante 6).
