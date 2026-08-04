# project

Carcaça de um **projeto consumidor** com uma **harness na raiz**. Este repositório é uma casca
genérica: um pequeno negócio de exemplo em `src/`, e ao redor dele uma harness declarativa que
orquestra análise, avaliação e evolução do negócio consumindo a **WebQA Suite** como padrão
externo e versionado.

O ponto de partida da arquitetura, em uma frase:

> **O projeto declara configuração e autorização; o padrão fornece o motor e as verificações.**

E o corolário que justifica tudo:

> **Uma trava que o vigiado pode desligar em silêncio não é uma trava.**

Por isso o código de verificação **não mora aqui**. Ele é declarado como dependência versionada
(`requirements-qa.txt`) e consumido pela harness — nunca copiado para dentro deste repositório.

> **Acabou de clonar? Comece por [`BOOTSTRAP.md`](BOOTSTRAP.md).**

## Molde e derivado

Este repositório tem dois papéis possíveis, declarados em `project.yaml:project.kind`:

| `kind` | Governa | Bloco `target` |
|---|---|---|
| `mold` | nada — é a casca genérica, reaproveitável por qualquer alvo | **proibido** pelo schema |
| `derived` | exatamente um alvo | **exigido** pelo schema |

`danzeroum/project` é o molde. Colar o link de um repositório de negócio numa sessão e rodar
`/adotar` deriva dele um **gêmeo de governança** — um repositório novo que declara o alvo em
`project.yaml:target`, ancora o commit exato em `target.lock` e materializa o código em
`workspace/target/` (efêmero, fora do versionamento).

O derivado **declara o alvo, nunca o copia** (ADR-008). É a mesma decisão do ADR-001 aplicada a
outro objeto: uma cópia deriva do original em silêncio, e o metadado passa a descrever com toda a
confiança um sistema que não existe mais. E **nenhum alvo é especial** — um nome, stack ou caminho
de alvo em `ci/` ou `harness/` reprova o CI, porque um molde com caminho especial funciona para
aquele alvo e falha calado nos outros.

## As três fronteiras de confiança

Três camadas, três donos da verdade diferentes. Confundi-las é o erro de governança desta
arquitetura.

| Camada | Onde vive | Dona da verdade | Contém |
|---|---|---|---|
| **Padrão — WebQA Suite** | `danzeroum/qa-suite` (repo externo) | julgamento de segurança | motor, `checks/`, lista curada de caminhos sensíveis, gates fail-closed, sanitização |
| **Projeto consumidor** | **este repositório** | autorização + configuração | alvo, thresholds, escopo autorizado, versão exata do padrão — **só declarativo** |
| **Harness** | raiz deste repositório (`harness/`) | orquestração | qual modo pode rodar, qual agente dispara, onde arquivar evidência |

A harness **consome** a suíte; ela não reimplementa os checks nem copia o motor. Isso preserva a
uniformidade do padrão e reduz a superfície de alteração local.

> ### Não copie a régua
> `webqa/`, `checks/` e `data/caminhos-sensiveis.yaml` **nunca** existem neste repositório. Se
> cada projeto tiver uma cópia editável da lista curada, alguém remove uma linha que dava trabalho,
> a suíte para de procurar aquilo, e **o laudo continua dizendo "nenhum achado"** — sem erro, sem
> aviso, indistinguível de um projeto seguro. A régua mora fora e é declarada por versão.

## Os dois trabalhos da suíte

| Trabalho | Objeto | Precisa de rede | Precisa de autorização | Agente pode disparar |
|---|---|---|---|---|
| **B — Inventário** | o código deste repositório (lê testes por AST) | não | não | ✅ sim |
| **A — Auditoria** | a aplicação publicada (o alvo) | sim | sim, conforme o modo | ⚠️ só passivo, com alvo já configurado |

Tratar os dois como a mesma coisa faria a harness pedir autorização de sondagem para rodar um
inventário — e o operador aprende a aprovar sem ler. Eles são modos distintos (ver
`harness/harness.yaml` e `WEBQA_CONSUMER_CONTRACT.md`).

## Layout

```
project/
├── project.yaml          identidade, criticidade, donos, governança (schema em harness/schemas/)
├── business/             visão + capacidades + rules/ (regras) + requirements/ (backlog por capacidade)
├── architecture/         componentes (+ requisitos que implementam) + interfaces + adr/ (decisões)
├── design/               sistema de design + superfícies de UI ligadas a capacidades
├── governance/           registro de riscos que classifica a mudança antes de agir
├── src/project/          negócio de exemplo (entrada real do inventário / Trabalho B)
├── tests/
│   ├── unit/             testes do negócio (o que o inventário cataloga)
│   └── qa/               configuração DECLARATIVA de consumo da suíte (alvo, escopo, campanha)
├── harness/              o plano de controle
│   ├── harness.yaml      modos + higiene de ambiente + protected_paths + decision_policy
│   ├── schemas/          contratos JSON (procedência, laudo, harness, project, risco, capacidade, componente)
│   ├── policies/         índice: cada regra aponta para seu fiscal executável
│   ├── agents/           contratos dos agentes (developer, reviewer, tester, documenter)
│   ├── prompts/          templates de tarefa
│   ├── change-proposals/ mudanças declaradas antes de executadas (ponte para execução agentic)
│   └── runs/ reports/ state/   evidência (gitignored)
├── ci/
│   ├── validate_all.py          um comando, um significado de "validado" (roda os quatro)
│   ├── validate_metadata.py     schema, IDs e coerência entre documentos
│   ├── audit_governance.py      asserções de ADR + cobertura das etapas
│   ├── audit_lgpd.py            inventário de dado pessoal + frescor do julgamento
│   ├── generate_graph.py        artefato derivado (docs/metadata-graph.md)
│   └── hooks/                   env-hygiene e guarda de caminho protegido, na sessão do agente
├── requirements-qa.txt   webqa-suite==1.0.0  (padrão DECLARADO, nunca copiado — FONTE ÚNICA da versão)
├── WEBQA_CONSUMER_CONTRACT.md   a interface entre este repo e a suíte
├── CLAUDE.md / .claude/         doutrina carregada em sessão de agente + hooks (ergonomia, não gate)
└── .github/
    ├── CODEOWNERS               o fiscal real dos protected_paths (com branch protection)
    └── workflows/
        ├── qa.yml               CI: inventário+passivo automáticos; carga/sondagem segregados
        ├── validate-metadata.yml  CI: validação total, filtrada por paths
        └── governance.yml       CI: validação total SEM filtro + passos negativos de mordida
```

## Metadados governáveis

O repositório descreve não só *como se verifica*, mas *o que o negócio é* — em camadas separadas por
dono e ciclo. Cada metadado tem **fonte de verdade, schema, dono e fiscal**; sem isso, YAML é só
comentário ("markdown que não morde").

- **Fonte única da versão:** o pin em `requirements-qa.txt` é o único lugar com o número. `project.yaml`,
  `tests/qa/config.yaml` e os demais **referenciam** (`version_source`), nunca restatam — fecha a
  deriva de régua (H3). O schema recusa estruturalmente escrever a versão em `project.yaml`.
- **Rastreabilidade por ID estável:** `CAP-*` (capacidade) → `CMP-*` (componente) → código → teste →
  risco. Arestas por ID, não por path — renomear arquivo não quebra a referência.
- **Maturidade condiciona o fiscal:** `ci/validate_metadata.py` só exige código+teste existentes para
  capacidades `implemented`/`verified`; uma `proposed` pode ainda não ter código.
- **Procedência versionada:** o schema da procedência evolui por versão (`1.0` → `1.1` adiciona o bloco
  `artifact`), nunca por um segundo formato informal.
- **Design como contrato:** `design/ui-surfaces.yaml` liga cada superfície de UI a uma capacidade
  (`CAP-*`) com critérios de aceite explícitos e aos requisitos que satisfaz (`satisfies: [REQ-*]`);
  o fiscal cobra que o requisito exista e compartilhe a mesma capacidade da superfície. O reviewer
  avalia mudança de UI contra a régua, não contra um palpite.
- **Mudança declarada antes de executada:** toda proposta (`harness/change-proposals/`) declara o que
  afeta, o risco e os gates; risco `high`/`critical` **exige aval humano** por trava de schema. É o elo
  entre metadado estático e execução agentic.
- **Regra de negócio ligada a teste:** `business/rules/*.yaml` declara a régua funcional de cada
  capacidade; uma regra `verified` aponta para o teste que a prova, e a capacidade referencia o arquivo
  de volta (elo bidirecional que o fiscal cobra).
- **Decisões versionadas:** `architecture/adr/` guarda os ADRs; o `index.yaml` é a parte fiscalizável —
  cada entrada aponta para um arquivo real e resolve suas referências a capacidade, componente
  (`related_components: [CMP-*]`), risco e ADR.
- **Backlog no centro do grafo:** `business/requirements/backlog.yaml` declara os requisitos, cada um
  ligado à sua `CAP-*`, às métricas (`MET-*`) que move, às regras (`RULE-*`) que o regem, aos testes que
  o validam (`validated_by`), e opcionalmente a `depends_on`/`risk`. O fiscal cobra que tudo resolva — e
  que métricas/regras/testes citados compartilhem a capacidade do requisito (e que só um requisito
  iniciado seja validado por teste). As métricas de sucesso vivem em `business/vision.yaml`; assim o
  backlog fecha a cadeia do resultado de negócio até o teste que prova a entrega.
- **Componente ↔ requisito que implementa:** `architecture/components.yaml` pode declarar
  `implements: [REQ-*]`; o fiscal cobra que o requisito exista, compartilhe a capacidade do componente
  e esteja de fato em construção/pronto (`in_progress`/`done`) — um componente não "implementa" um
  requisito ainda proposto.
- **Interfaces coerentes com o grafo:** `architecture/interfaces.yaml` liga provedor e consumidores
  (`CMP-*`); o fiscal cobra que os símbolos expostos existam no provedor e que cada consumidor
  declare `depends_on` o provedor.
- **Mapa gerado dos IDs:** `docs/metadata-graph.md` é um diagrama Mermaid **gerado** por
  `ci/generate_graph.py` a partir dos metadados — artefato derivado, mantido em dia pelo CI
  (`--check`), nunca uma fonte manual paralela.
- **Decisão com asserção executável:** cada ADR declara `assertions[]` em
  `architecture/adr/index.yaml` — afirmações tipadas sobre o repositório real, executadas por
  `ci/audit_governance.py`. ADR `accepted` sem asserção é recusado pelo schema, e asserção cujo
  alvo não existe vira `assertion_unresolvable`: uma trava que não encontra o que vigiar está
  quebrada, não satisfeita. É o que fecha o vão entre "o ADR-005 decide inversão de dependência"
  e "o CI reprova quando `pricing.py` importa o adaptador concreto".
- **Todas as etapas com fiscal:** `harness/stages.yaml` enumera as treze etapas do projeto com
  seus artefatos e fiscais. O fiscal cobra que cada artefato exista, que cada `enforced_by`
  resolva (com `::simbolo`, por AST) e que **todo arquivo do repositório pertença a exatamente
  uma etapa ou a uma isenção justificada**. É a partição que faz cobertura ser invariante em vez
  de aspiração: diretório novo exige declarar a que etapa pertence.
- **LGPD sempre ligada, em dois níveis:** `ci/audit_lgpd.py` roda a cada push sobre o projeto
  inteiro — registro das operações (Art. 37), varredura de tratamento-sombra, coerência do papel
  declarado, direitos do titular com endpoint (Art. 18) e frescor do julgamento por fingerprint
  de conteúdo (Art. 38). Duas travas são estruturais no schema: dado sensível não admite legítimo
  interesse (Art. 11) e papel de tratador exige encarregado (Art. 41). **O fiscal determinístico
  não julga legalidade** — ele garante que o julgamento (skill `/revisao-lgpd`, agente `privacy`)
  existe, é do tipo certo e cobre este estado do repositório.

## Quickstart

```bash
pip install -e ".[dev]"     # instala o pacote de negócio + ferramentas de teste
pytest                      # negócio (tests/unit) + mordida dos fiscais (tests/governance)
python ci/validate_all.py   # metadados + grafo + conformidade + LGPD — o mesmo comando do CI
```

A régua é declarada em `requirements-qa.txt` na versão real (`webqa-suite==1.0.0`). Como a suíte
ainda **não é publicada no PyPI**, a instalação é feita a partir do Git e — como a v1.0.0 ainda não
tem CLI instalável — a execução é por marcadores `pytest` / `make` / container Docker (ver
`docs/COMO-ADOTAR.md`). Os passos de suíte no CI (`.github/workflows/qa.yml`) degradam de forma
tolerante enquanto o ambiente não tiver a suíte instalada.

## Onde a trava realmente morde

Este é um **esqueleto declarativo**: não há orquestrador Python nesta casca. A enforcement efetiva
vive em camadas declarativas reais, não em markdown:

1. **CI (`.github/workflows/qa.yml`)** — o bloco `env:` aplica a denylist `WEBQA_*` com um passo
   negativo que prova o abort; os modos `load` e `active_discovery` só existem em jobs segregados
   `workflow_dispatch` com revisores obrigatórios.
2. **Suíte externa** — os gates fail-closed por variável de ambiente. O índice em
   `harness/policies/` aponta para cada um deles.

Ver `WEBQA_CONSUMER_CONTRACT.md` para o contrato completo.
