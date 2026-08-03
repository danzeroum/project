# ADR-003 — Versão do padrão em fonte única e procedência carimbada

- **Status:** accepted
- **Data:** 2026-08-03
- **Capacidades relacionadas:** CAP-PRICING
- **Riscos relacionados:** RISK-DEP-001

## Contexto

Dois laudos que dizem "0 achados" podem afirmar coisas diferentes se foram produzidos por versões
diferentes da régua, ou por listas curadas diferentes. Se a versão do padrão for restatada em vários
arquivos de metadado, essas cópias derivam, e a comparação entre projetos passa a mentir sem que
ninguém perceba (risco H3).

## Decisão

- A versão do padrão mora em **um único lugar**: o pin em `requirements-qa.txt`. Os demais metadados
  (`project.yaml`, `tests/qa/config.yaml`, …) **referenciam** via `version_source`, nunca restatam. O
  schema recusa estruturalmente escrever o número em `project.yaml`.
- Todo laudo carrega procedência: versão, commit e `sensitive_paths_hash` da lista curada. A agregação
  recusa comparar réguas incompatíveis ("não comparável" é um resultado válido).
- Subir de versão é decisão versionada, num PR, com o laudo anterior e o novo lado a lado.

## Consequências

- O único espelho tolerado (`config.yaml.standard_version`) existe sob verificação de CI de igualdade.
- Uma lista curada editada localmente aparece como divergência de hash, não como silêncio.
- A harness pode propor a subida de versão; nunca executá-la sozinha.

## Fiscal

`ci/validate_metadata.py::check_version_single_source`, `harness/schemas/provenance.schema.json`,
`harness/policies/provenance.md`, `harness/policies/dependency-updates.md`.
