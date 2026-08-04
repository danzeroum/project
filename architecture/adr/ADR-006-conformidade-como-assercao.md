# ADR-006 — Conformidade declarada como asserção executável, e etapa sem fiscal é achado

- **Status:** accepted
- **Data:** 2026-08-04
- **Riscos relacionados:** RISK-CONF-001, RISK-STAGE-001

## Contexto

Os cinco ADRs anteriores terminam numa seção `## Fiscal` que nomeia, em prosa, quem os aplica. É
uma melhoria real sobre não dizer nada — e ainda assim é prosa. Entre "o ADR-005 decide que a
precificação depende da porta" e "o CI reprova quando `pricing.py` importa o adaptador concreto"
não havia nada. Uma decisão podia permanecer `accepted` enquanto o código fazia outra coisa: sem
erro, sem aviso, indistinguível de um projeto conforme. É o mesmo modo de falha que o ADR-002
descreve para metadados, reencarnado uma camada acima — na camada que deveria garanti-lo.

O segundo buraco era de escopo. `ci/validate_metadata.py` fiscaliza os arquivos que estão na sua
lista `DOCS`. Nada dizia quais **etapas** do projeto existem, nem obrigava cada uma a ter fiscal.
Cobertura era afirmada em prosa e nunca verificada; um diretório novo simplesmente não era
fiscalizado por ninguém, e o silêncio parecia aprovação.

## Decisão

**1. Toda decisão declara asserções tipadas.** Cada entrada de `architecture/adr/index.yaml`
traz `assertions[]` — `path_absent`, `path_present`, `import_required`, `import_forbidden`,
`file_matches`, `file_lacks`, `schema_lock`, `manual` — executadas por `ci/audit_governance.py`
a cada push. ADR `accepted` sem asserção é recusado pelo schema (`if/then` com `minItems: 1`).

**2. Alvo inexistente é achado, nunca aprovação.** Uma asserção cujo glob casa zero arquivos
"passa" sem verificar nada. `assertion_unresolvable` fecha essa porta: trava que não encontra o
que vigiar está quebrada, não satisfeita.

**3. Severidade é triagem, não gate.** Com fail-closed, qualquer achado derruba o CI. A
severidade ordena o laudo e informa a decisão humana; ela nunca filtra. Um `fail_on_severity`
configurável seria precisamente a trava que o vigiado desliga em silêncio.

**4. As etapas do projeto são um manifesto verificável.** `harness/stages.yaml` enumera as
etapas com seus artefatos e fiscais. É índice, não segunda descrição: referencia caminhos e
símbolos, nunca IDs — o schema recusa estruturalmente quem tentar restatá-los. Três checagens
fecham a cobertura: artefato casa arquivo real; fiscal resolve (com `::simbolo`, por AST); e
todo arquivo do repositório pertence a exatamente uma etapa ou a uma isenção declarada com
justificativa.

**5. O laudo tem contrato próprio.** `harness/schemas/audit-report.schema.json` é irmão de
`report.schema.json`, não derivado: aquele carrega a procedência do padrão externo WebQA, e
forçar os fiscais locais naquele envelope produziria campos mentirosos. O fiscal valida o
próprio laudo antes de gravá-lo — emitir laudo fora do contrato seria a versão executável de
"markdown que não morde".

## Consequências

- Quebrar a inversão de dependência do ADR-005 deixa de ser possível em silêncio: vira passo
  vermelho, com o `assertion.id` na mensagem apontando a linha exata de `index.yaml`.
- Cada ADR novo custa ao menos uma asserção — ou uma `manual` com justificativa. É deliberado.
- Diretório novo passa a exigir declaração de etapa. Também deliberado: é o que impede área do
  projeto crescer fora de qualquer fiscalização.
- O que AST estático não alcança (import dinâmico via `importlib`) não some: aparece no laudo
  como asserção `manual`, em vez de ficar tacitamente fora do escopo.
- Custo assumido: `ci/audit_governance.py` fiscaliza a si mesmo por meio de `ADR-002-A3` e do
  `enforced_by` de `STAGE-DECISIONS`. Auto-referência só é honesta com prova externa — daí o
  teste negativo que renomeia `check_adr_conformance` e exige que o CI reprove.

## Fiscal

`ci/audit_governance.py` (executa as asserções, a resolução de fiscais e a partição de etapas);
`harness/schemas/adr-index.schema.json` (`accepted` ⇒ `assertions` com `minItems: 1`);
`harness/schemas/stages.schema.json` (artefato não pode ser ID);
`harness/policies/conformance.md`; `.github/workflows/governance.yml` (passos negativos que
provam a mordida).
