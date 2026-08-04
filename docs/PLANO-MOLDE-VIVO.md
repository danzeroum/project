# Plano — `danzeroum/project` como molde vivo: colar um link e nascer o gêmeo de governança

## Contexto

O repositório é hoje uma **casca de governança madura, mas passiva**: 21 metadados com schema,
7 ADRs com 30 asserções executáveis, 13 etapas com fiscal resolvível, 4 fiscais em
`ci/validate_all.py` e ~40 testes que provam que cada fiscal morde. O que falta é o caminho de
entrada — quem clona não é levado a lugar nenhum, e nada transforma código em metadado.

Adoto o modelo do **PLANO-HARNESS-VIVA-v2** anexado, que resolve a ambiguidade que eu tinha
deixado em aberto (onde os metadados moram):

| Papel | Repositório | O que é |
|---|---|---|
| **MOLDE** | `danzeroum/project` | a casca: schemas, fiscais, políticas, agentes, comandos |
| **ALVO** | qualquer repo de negócio | intocado; referenciado por SHA, nunca copiado |
| **DERIVADO** | `project-<alvo>` | molde + metadados DO alvo: o gêmeo de governança |

Decisão estruturante: **o derivado declara o alvo, nunca o copia** — mesma lógica da régua. O
código do alvo materializa em `workspace/target/` (gitignored) no SHA de um `target.lock`; o
derivado versiona só o que é dele: metadados, laudos e o lock.

**Escopo desta entrega, conforme você confirmou: apenas `danzeroum/project`.** O alvo e o derivado
são parâmetros do sistema, não repositórios desta tarefa. Construímos aqui a máquina; ela é
exercitada contra um alvo sintético descartável, não contra um repo real. Fases **A→B→C** (o
caminho crítico: com elas, colar um link já produz derivado validado com a invariante do código
órfão mordendo). **D–G ficam especificadas** ao final, para PRs seguintes.

### A invariante da genericidade — e como ela morde

**Nenhum alvo é especial.** O molde tem que funcionar para qualquer repositório que você
compartilhe, sem edição prévia: qualquer linguagem, qualquer layout, monorepo ou não, com ou sem
testes. Concretamente, isso proíbe três coisas no molde e cada proibição vira fiscal, não parágrafo:

1. **Nada específico de alvo no molde.** Nome de repositório, stack, gerenciador de pacotes ou
   caminho de código não aparecem em `ci/` nem em `harness/`. Fiscalizado por uma asserção
   `file_lacks` no ADR-008 — se alguém "resolver" um alvo difícil cravando o nome dele num fiscal,
   o CI reprova. É o mesmo princípio do "não restatar a versão da régua", aplicado ao alvo.
2. **Descobrir, nunca presumir.** `code_roots`, linguagem, branch padrão e onde ficam os testes são
   **descobertos** no reconhecimento e **declarados** em `target`, não chutados por convenção.
3. **Ignorância é achado, não silêncio.** Linguagem sem adapter reprova com exit 2 ("fiscal não
   conseguiu fiscalizar") e diz o que não sabe ler. Um inventário que passa verde porque não
   entendeu o código é a pior falha possível neste repositório.

Você não teve preferência quanto ao canal de retorno derivado → alvo: fica **desligado por
padrão**, como chave declarada em `harness/harness.yaml`, coerente com o `decision_policy.default:
deny` do próprio repo. Escrita em repositório de terceiro começa fechada e liga por decisão.

### Governança desta mudança

Toda fase toca caminhos protegidos (`harness/`, `ci/`, `.github/`, `.claude/`, `CLAUDE.md`). Por
ADR-004, cada fase começa por uma **change-proposal** em `harness/change-proposals/`, validada
antes de executada — CP-004 (A), CP-005 (B), CP-006 (C) — cada uma virando um PR. A Fase C é risco
`high`: ela muda o significado de "verde" (código órfão passa a reprovar), e o schema força
`human_approval_required: true`.

---

## Bloqueios reais verificados no código (o v2 não os menciona)

Levantados lendo o repositório, não presumidos. Cada um vira trabalho explícito abaixo.

1. **`source_paths` fora de `src/` reprova hoje.** `ci/validate_metadata.py::check_capabilities`
   exige literalmente `p.startswith("src/")` e `p.startswith("tests/")`. Metadado do derivado
   aponta para `workspace/target/...` — **sem mudar esse fiscal, o modelo v2 não passa no próprio
   CI.** É o bloqueio nº 1 e ele mora na Fase C.
2. **`project.schema.json` é `additionalProperties: false`** com 8 chaves obrigatórias. Os campos
   `kind: mold|derived` e o bloco `target` exigem alteração de schema em caminho protegido.
3. **`criticality` seria sinônimo redundante.** `capabilities.schema.json` já exige `risk_level`
   (e é `additionalProperties: false`). A Fase E do v2 propõe `criticality` — **reusar
   `risk_level`**; duas escalas para a mesma coisa é exatamente a deriva que este repo combate.
4. **`risk-register.schema.json` é fechado**, e `area` é um enum de 6 valores
   (`webqa, dependencies, data, access, availability, governance`). O campo `related` e quaisquer
   áreas novas exigem alteração declarada. Nota: `availability` existe e **nenhum risco a usa** —
   sintoma do que o pedido aponta.
5. **Um clone fresco quebra o hook `SessionStart`.** `pyyaml` e `jsonschema` só existem no extra
   `[dev]` do `pyproject.toml`. Logo `ci/bootstrap.py` **precisa ser stdlib puro** na sua primeira
   fase — ele não pode depender do que ainda vai instalar.
6. **`check_repo_partition` reprova diretório novo não declarado.** Tudo que nasce precisa de etapa
   ou isenção: `BOOTSTRAP.md`, `target.lock`, `workspace/`, `.claude/commands/`, `harness/pipeline/`.
7. **Sem `gh` CLI neste ambiente**, e o `create_repository` do MCP do GitHub não aceita template.
   O `/adotar` cria vazio via MCP e empurra a casca no primeiro commit — mesmo efeito prático
   (histórico limpo), outro caminho. Marcar o molde como Template deixa de ser pré-requisito.
8. **`generated_from` ≠ `derived_from`.** O cabeçalho de todo metadado já tem `generated_from`, com
   um `oneOf` em cada schema (`source_of_truth: false` ⇒ `generated_from` string) — é o mecanismo
   pronto para metadado derivado, no nível do arquivo. O `derived_from` do v2 é no nível do item
   (`repo`, `sha`, `path`, `section`). Os dois convivem e não devem colidir.
9. **CP-000 (tirar o negócio de exemplo) roda no DERIVADO, não aqui.** As asserções de ADR-005
   (`import_required`, `import_forbidden`, `file_matches`, `path_present`) apontam para
   `src/project/*`; apagar esses arquivos torna as asserções `assertion_unresolvable`. Logo o
   CP-000 do derivado precisa **também** dar `superseded` no ADR-005 e remover `CAP-PRICING`,
   `CAP-CATALOG`, `CMP-*`, `RULE-*`, `UI-*`, `REQ-*` e os artefatos de `STAGE-CODE`/`STAGE-TESTS`.
   O molde mantém tudo — é o substrato mínimo que faz as asserções morderem.

---

## Fase A — Derivação: colar o link e nascer o gêmeo · CP-004

*Pronto quando: link de um alvo → derivado criado, ancorado por `target.lock` e validado.*

- **`BOOTSTRAP.md` (raiz)** — o caminho que a harness valida inicialmente, em ordem executável,
  para o agente que chegou só com um link: *"isto é um molde; se você recebeu um link de ALVO, rode
  `/adotar`; se está num derivado, rode `/bootstrap`"*. Uma página. Por ADR-002 **não restata o
  pipeline** — a lógica mora nos scripts e em `harness/pipeline/`.
- **`.claude/commands/adotar.md`** — `/adotar <url-de-qualquer-alvo>`, ponto de entrada único.
  Recebe o link **cru** que você compartilhar e não presume nada sobre ele:
  1. **traz o alvo para o escopo da sessão** via `add_repo` — o escopo do GitHub nesta sessão é
     limitado a `danzeroum/project`, então adotar qualquer outro repositório passa obrigatoriamente
     por aí. Sem acesso, o comando para e diz exatamente o que pedir, em vez de falhar adiante;
  2. **reconhece o alvo**: branch padrão real (não presumida `main`), linguagens presentes,
     candidatos a `code_roots`, onde ficam os testes, se é monorepo. Tudo vira proposta a confirmar;
  3. normaliza o nome → `project-<nome-real-do-alvo>`;
  4. procura o derivado; se não existe, cria vazio via `mcp__github__create_repository` e empurra
     a casca do molde (bloqueio 7);
  5. clona o derivado, escreve `project.yaml: kind: derived` + `target` + `target.lock` no HEAD do
     alvo;
  6. abre o **CP-000** inaugural — remove o negócio de exemplo *e* dá `superseded` no ADR-005
     (bloqueio 9);
  7. encadeia `/bootstrap`.
- **`project.schema.json` estendido** (bloqueio 2): `kind: mold | derived`; bloco `target`
  (`repo`, `ref`, `code_roots[]`, `languages[]`) **obrigatório quando `derived`, proibido quando
  `mold`** — o schema distingue estruturalmente os dois papéis, em vez de um comentário pedindo bom
  senso. `code_roots` e `languages` são preenchidos pelo reconhecimento e conferidos contra o
  workspace: raiz declarada que não existe no alvo é achado.
- **`target.lock`** (raiz, versionado) — o SHA exato ingerido. Fonte única da versão do alvo,
  exatamente como `requirements-qa.txt` é da régua; nenhum outro arquivo restata o SHA.
- **`workspace/`** — gitignored com `.gitkeep`, no padrão já usado por `harness/runs|reports|state`.
- **ADR-008 — "O derivado declara o alvo, nunca o copia; e nenhum alvo é especial"**, com
  asserções: `path_present` (`BOOTSTRAP.md`, `.claude/commands/adotar.md`); `schema_lock` sobre o
  `if/then` de `kind`↔`target`; `file_lacks` proibindo SHA de alvo fora de `target.lock`; e
  `file_lacks` sobre `ci/**` e `harness/**` proibindo nome de alvo, stack ou caminho de código
  cravado — a invariante da genericidade, mordendo.
- **Etapas** (bloqueio 6): `BOOTSTRAP.md` → artefatos de `STAGE-DOCS`; `target.lock` e
  `.claude/commands` → `STAGE-CI-HARNESS`; `workspace/` → isenção declarada em `ungoverned` com
  justificativa (materialização efêmera, como a evidência).
- **Mordida:** `project.yaml` com `kind: derived` sem `target` → `validate_all.py` sai 1.

## Fase B — Bootstrap do derivado: cold start idempotente · CP-005

*Pronto quando: sessão nova → workspace no SHA do lock + laudo de estado.*

- **`ci/bootstrap.py`** — **stdlib puro** (bloqueio 5), idempotente:
  (a) valida ambiente (python, git, e as toolchains do alvo declaradas em `target`);
  (b) instala as dependências dos fiscais;
  (c) materializa `workspace/target/` no SHA do lock (clone raso + checkout; re-execução só faz
  fetch);
  (d) roda `ci/validate_all.py`;
  (e) emite `harness/state/bootstrap-<data>.json` sob um `bootstrap-report.schema.json` novo, com
  estado e próximo passo. Preserva os exit codes 0/1/2.
- **`SessionStart` tolerante** — hoje o hook falha mudo num clone fresco. Passa a tentar
  `validate_all --summary` e, faltando ambiente ou workspace, imprimir *"rode `/bootstrap`"*.
  Ergonomia; o gate continua sendo `governance.yml`.
- **`.claude/commands/bootstrap.md`**.
- **`ci/bootstrap.py --check-drift`** — compara o HEAD remoto de `target.ref` com `target.lock` e
  reporta a fila de commits não ingeridos. É o insumo da Fase F.

## Fase C — Inventário multi-linguagem e a invariante do código órfão · CP-006 · risco `high`

*Pronto quando: arquivo novo no alvo sem `CMP-*` reprova, com mordida testada.*

Esta é a fase que responde ao "todo o código compartilhado transformado em documentação".

- **Desbloquear o fiscal (bloqueio 1, primeiro commit da fase).**
  `check_capabilities`/`check_components` passam a validar prefixo contra as raízes declaradas:
  `src/`+`tests/` quando `kind: mold`, `workspace/target/<code_roots>` quando `kind: derived`.
  Sem isso nada da Fase C compila conceitualmente.
- **`ci/inventory_code.py` — dispatcher por linguagem** sobre `workspace/target/`:
  - adapter **python** (AST — reusa `ci/harness_lib.py`, que já faz caminhada de AST, glob,
    fingerprint sha256 e o acumulador `Findings`, e espelha `audit_lgpd.py::scan_personal_data`);
  - adapter **typescript/javascript** (o grosso do esforço, e o mais provável num alvo qualquer):
    módulos, exports e imports internos resolvidos via `tsconfig`/workspace do gerenciador de
    pacotes; `dependency-cruiser` como dev-dependency do derivado, com fallback de parser próprio
    de imports;
  - **adapter genérico de fallback**: sem entender semântica, mapeia arquivos e diretórios para
    componentes candidatos. Cobre a invariante do código órfão (que é sobre *pertencimento*, não
    sobre imports) em **qualquer** linguagem, e declara no laudo que as arestas de dependência
    ficaram por fazer;
  - saída normalizada única `harness/state/code-inventory.json` (gitignored) + `--check`.
  Adapter é **plugin registrado**, não `if` novo — acrescentar linguagem não edita o dispatcher.
  Linguagem sem adapter semântico cai no fallback e **declara o que não sabe ler**; se nem o
  fallback se aplicar, sai 2 ("fiscal não conseguiu fiscalizar"). Nunca passa em silêncio.
- **Quatro checks novos em `ci/validate_metadata.py`**, cada um com teste de mordida:
  - **código órfão** — todo arquivo sob `target.code_roots` pertence a `source_paths` de
    exatamente um `CMP-*`, ou a uma isenção justificada em `components.yaml: exemptions[]`
    (mesmo padrão de `stages.yaml:ungoverned`, incluindo isenção morta virar achado);
  - **teste órfão** — todo teste do alvo é referenciado por algum `tested_by`/`validated_by`;
  - **dependência real ⊆ declarada** — o grafo de imports projetado em componentes cabe em
    `depends_on`; import não declarado **acusa**, `depends_on` sem import vira aviso;
  - **`exposes` verificado** — cada símbolo declarado existe de fato no workspace.
- **Nenhum metadado derivado nasce como verdade.** O inventário escreve
  `source_of_truth: false` + `generated_from` (bloqueio 8) e **nunca preenche campo de julgamento**
  (`purpose`, `risk_level`, `likelihood`, `impact`, base legal): ficam vazios e o fiscal recusa a
  promoção enquanto estiverem. Promover é ato humano/agente — é o que mantém "o projeto declara".
- **ADR-009 — "Código sem metadado não existe"**; política
  `harness/policies/code-metadata.md` terminando em `Fiscalizado por:` resolvível.
- **Risco novo** `RISK-INGEST-001` (`area: governance`): metadado derivado do código passa por
  declarado e ninguém julga. Controles: `ci/inventory_code.py`, o check de frescor, a política,
  ADR-009.

## Prova de fogo desta entrega

Contra **alvos sintéticos descartáveis** criados no scratchpad (não contra repos reais). Um alvo
só não prova genericidade, então são três, deliberadamente diferentes entre si:

| Alvo sintético | O que ele prova |
|---|---|
| pacote Python de um módulo só, com testes | o caminho feliz e o adapter nativo |
| monorepo TS com dois pacotes e imports cruzados | `code_roots` múltiplos e o grafo de dependência |
| repo numa linguagem sem adapter (ex.: Go) | o fallback genérico morde, e o laudo declara o que não leu |

Em cada um: container limpo → `/adotar <alvo>` → derivado ancorado → `/bootstrap` → workspace no
SHA → `validate_all.py` verde. Depois, commit sintético com um arquivo novo no alvo → o inventário
acusa o órfão. É o mesmo truque de `HARNESS_REPO_ROOT` que `tests/governance/conftest.py` já usa
para provar que um fiscal morde — agora atravessando repositórios.

**Critério de pronto da genericidade:** os três passam sem que nenhuma linha de `ci/` ou `harness/`
mencione qualquer um deles.

---

## Fases seguintes (especificadas, fora desta entrega)

- **D — Ingestão documental.** `harness/pipeline/ingest.yaml` (+schema, fases com `inputs`,
  `outputs`, `agent`, `fiscal` resolvível pela mecânica de `stages.yaml`); agente novo
  `harness/agents/cartographer/`; campo `derived_from: {repo, sha, path, section}` nos schemas
  relevantes, com o fiscal cobrando que o caminho exista no SHA do lock; decisões e pendências do
  alvo viram ADRs e backlog do derivado. `/ingerir`. ADR-010.
- **E — Alinhamento e cobertura reversa de risco.** `ci/alignment_report.py` →
  `docs/alignment.md` derivado com `--check` (protegido contra edição manual como o grafo). É a
  direção que hoje não existe: `check_risk_control_coverage` só verifica que controles apontam para
  algo real, nunca que todo ativo é apontado por algum risco. R1 capacidade `risk_level: high` tem
  `RISK-*`; R2 risco `open` exige `treatment`+`owner`+prazo (*mitigado ou anotado, nunca mudo*);
  R3 `UI-*` órfã acusa; R4 `CMP-*` `verified` coberto por regra/requisito com teste.
  `risk-register.yaml` ganha `related: [CAP-/CMP-/REQ-*]` (bloqueio 4) e **reusa `risk_level`**
  (bloqueio 3). ADR-011.
- **F — Conformidade contínua e `/sincronizar`.** Agente `harness/agents/conformance/` para o
  julgamento semântico que o fiscal determinístico não faz; fingerprint generalizado em
  `harness_lib.py` (metadados + SHA do lock); `--check-drift` → diff de ingestão → change-proposal
  → o lock avança. `.github/workflows/conformance.yml` semanal. Canal de retorno ao alvo como
  chave **`false`** em `harness.yaml`. ADR-012.
- **G — `security/` como departamento.** Dos departamentos que você citou, `architecture/`,
  `business/`, `design/` e `governance/` existem; **segurança não existe como camada** — só difusa,
  num `security_owner` e no `RISK-META-002`. `security/threat-model.yaml` (STRIDE por
  componente/interface, `mitigations[]` tipadas como os `controls[]`, `residual_risk` → `RISK-*`) e
  `security/dependencies.yaml` (SBOM leve: dependência instalada e não inventariada é achado).
  Custa 2 schemas + 2 entradas em `DOCS` + `STAGE-SECURITY` + política.

## Arquivos

**Novos:** `BOOTSTRAP.md`, `target.lock`, `workspace/.gitkeep`,
`.claude/commands/{adotar,bootstrap}.md`, `ci/{bootstrap,inventory_code}.py`,
`ci/adapters/{__init__,python,typescript,generico}.py` (registro de plugins),
`harness/schemas/bootstrap-report.schema.json`, `harness/policies/code-metadata.md`,
`architecture/adr/ADR-00{8,9}-*.md`,
`tests/governance/test_{derivacao,bootstrap,inventario}_bites.py`,
`harness/change-proposals/CP-00{4,5,6}-*.yaml`.

**Alterados:** `harness/schemas/project.schema.json` (`kind`+`target`), `project.yaml`
(`kind: mold`), `ci/validate_metadata.py` (prefixo por raiz declarada + 4 checks novos),
`ci/harness_lib.py`, `harness/stages.yaml` (artefatos e isenção novos),
`architecture/adr/index.yaml`, `governance/risk-register.yaml`, `harness/harness.yaml`,
`.claude/settings.json`, `.github/workflows/governance.yml` (passos negativos novos),
`.gitignore`, `README.md`, `CLAUDE.md`, `docs/COMO-ADOTAR.md` (passa a referenciar o pipeline, não
a defini-lo; o passo 7 deixa de ser "opcional").

## Verificação

Ao fim de **cada fase** — é exatamente o que `.github/workflows/governance.yml` roda:

```bash
python ci/validate_all.py            # 0 conforme · 1 divergência · 2 fiscal não fiscalizou
pytest tests/governance -q           # os fiscais mordem quando devem
pytest tests/unit -q
python ci/generate_graph.py --check  # derivado em dia
```

Novo desta entrega:

```bash
python ci/bootstrap.py --check-drift
python ci/inventory_code.py --check
```
