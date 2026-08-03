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
├── src/project/          negócio de exemplo (entrada real do inventário / Trabalho B)
├── tests/
│   ├── unit/             testes do negócio (o que o inventário cataloga)
│   └── qa/               configuração DECLARATIVA de consumo da suíte (alvo, escopo, campanha)
├── harness/              o plano de controle
│   ├── harness.yaml      modos de execução + higiene de ambiente
│   ├── schemas/          contratos JSON (procedência, laudo, harness.yaml)
│   ├── policies/         índice: cada regra aponta para seu fiscal executável
│   ├── agents/           contratos dos agentes (developer, reviewer, tester, documenter)
│   ├── prompts/          templates de tarefa
│   └── runs/ reports/ state/   evidência (gitignored)
├── requirements-qa.txt   webqa-suite==0.0.0  (padrão DECLARADO, nunca copiado)
├── WEBQA_CONSUMER_CONTRACT.md   a interface entre este repo e a suíte
└── .github/workflows/qa.yml     CI: inventário+passivo automáticos; carga/sondagem segregados
```

## Quickstart

```bash
pip install -e ".[dev]"     # instala o pacote de negócio + ferramentas de teste
pytest tests/unit           # o alvo do inventário é código real e testado
```

A execução da suíte (inventário e auditoria) é feita pela CLI externa `webqa`, orquestrada pelo CI
em `.github/workflows/qa.yml`. Enquanto o pacote `webqa-suite` não estiver publicado, o pin em
`requirements-qa.txt` é um placeholder (`==0.0.0`) e os passos de suíte no CI degradam de forma
tolerante.

## Onde a trava realmente morde

Este é um **esqueleto declarativo**: não há orquestrador Python nesta casca. A enforcement efetiva
vive em camadas declarativas reais, não em markdown:

1. **CI (`.github/workflows/qa.yml`)** — o bloco `env:` aplica a denylist `WEBQA_*` com um passo
   negativo que prova o abort; os modos `load` e `active_discovery` só existem em jobs segregados
   `workflow_dispatch` com revisores obrigatórios.
2. **Suíte externa** — os gates fail-closed por variável de ambiente. O índice em
   `harness/policies/` aponta para cada um deles.

Ver `WEBQA_CONSUMER_CONTRACT.md` para o contrato completo.
