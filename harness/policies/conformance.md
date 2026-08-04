# Política: conformidade entre decisão e repositório

Um ADR descreve uma decisão e termina numa seção `## Fiscal` que nomeia, **em prosa**, quem a
aplica. Prosa não executa. Entre "o ADR-005 decide que a precificação depende da porta" e "o CI
fica vermelho quando `pricing.py` importa o adaptador concreto" havia um vão inteiro, e nesse vão
uma decisão pode ficar `accepted` por meses enquanto o código faz outra coisa — sem erro, sem
aviso, indistinguível de um projeto conforme.

## A regra

Toda entrada de `architecture/adr/index.yaml` declara `assertions[]`: afirmações **tipadas** sobre
o repositório real, executadas a cada push. Um ADR `accepted` sem nenhuma asserção é recusado pelo
schema — é a aplicação recursiva do ADR-002 à camada que deveria garanti-lo.

Espécies: `path_absent`, `path_present`, `import_required`, `import_forbidden`, `file_matches`,
`file_lacks`, `schema_lock` e `manual`.

## As três armadilhas que esta política fecha

1. **Aprovação por vacuidade.** Uma asserção cujo glob casa zero arquivos "passa" sem verificar
   nada. `assertion_unresolvable` transforma alvo inexistente em achado — porque uma trava que
   não encontra o que vigiar não é uma trava satisfeita, é uma trava quebrada.
2. **Severidade virando gate.** Com fail-closed, **qualquer** achado, de qualquer severidade,
   derruba o CI. A severidade ordena o laudo e informa a decisão humana; ela nunca filtra. Um
   `fail_on_severity` configurável seria exatamente a trava que o vigiado desliga em silêncio.
3. **Declarar o inverificável por omissão.** O que AST estático não alcança — import dinâmico via
   `importlib.import_module` com nome montado em runtime — não some: entra como asserção `manual`
   com justificativa obrigatória e aparece no laudo. Quem quiser fechar essa porta declara um
   `file_lacks` com padrão `importlib\.import_module` sobre o glob do domínio.

## Cobertura das etapas

`harness/stages.yaml` enumera as etapas do projeto e, para cada uma, seus artefatos e seus
fiscais. Ele é um **índice**, não uma segunda descrição: referencia caminhos e símbolos, jamais
IDs (o schema recusa). Três checagens fecham a cobertura — artefato casa arquivo real, fiscal
resolve (com `::simbolo`, por AST), e **todo arquivo do repositório pertence a exatamente uma
etapa ou a uma isenção declarada com justificativa**. É a partição que faz "todas as etapas" ser
invariante em vez de aspiração: diretório novo passa a exigir declaração de etapa.

## Limite honesto

`.claude/settings.json` é uma trava que o vigiado pode editar. Por isso `.claude/`, `CLAUDE.md`,
`ci/` e `governance/` entraram em `protected_paths`, e por isso a fonte de verdade da enforcement
continua sendo `.github/workflows/governance.yml` mais branch protection. Os hooks são ergonomia
e feedback rápido — nunca o gate.

---

Fiscalizado por: `ci/audit_governance.py` (executa as asserções e a partição de etapas);
`harness/schemas/adr-index.schema.json` (ADR `accepted` exige `assertions` com `minItems: 1`);
`harness/schemas/stages.schema.json` (artefato não pode ser ID); `.github/workflows/governance.yml`.
Declarado em: `architecture/adr/index.yaml`, `harness/stages.yaml`.
Falha como: divergência entre decisão e repositório ⇒ achado no laudo e exit 1; fiscal incapaz de
fiscalizar ⇒ exit 2.
