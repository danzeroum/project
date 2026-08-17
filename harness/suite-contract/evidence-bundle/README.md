# Evidence Bundle do Produtor PSE — contrato de análise preparatória

> Sprint 6.2 — Reconciliação Pós-Merge da PSE.
> Proposta: `harness/change-proposals/CP-051-assurance-evidence-candidate.yaml`
> Decisão: `architecture/adr/ADR-032-evidence-bundle-candidate.md`

## O que é

Um **bundle de evidência** é um `evidence-bundle/v1 draft` produzido pela pse-suite. A PR #2 foi
mergeada em 17/08/2026 20:23:21 UTC — o produtor está no `main` da pse-suite (commit
`443da92d…`), mas **sem release**: não existe tag `v0.4.0`, manifesto de release ou pin
versionado. O estado declarado é **`merged_unreleased`** no `compatibility-matrix.yaml` (o
*assurance lock*).

A referência do produtor é **fechada** pelo schema
`harness/schemas/evidence-reference.schema.json` a três estados controlados:

| Estado | `release_eligible` | Exigência |
|---|---|---|
| `candidate_not_merged` | `false` (const) | — |
| `merged_unreleased` | `false` (const) | — |
| `released` | `true` (const) | bloco `release` com tag, versão, commit, manifesto e hash de artefato verificáveis |

**Merge no main ≠ release publicado ≠ dependência elegível para produção.** Um produtor em
`candidate_not_merged` ou `merged_unreleased` não é dependência elegível, e `released` só é
expresso com os metadados de release — nada fora destes três estados existe como opção de erro.

O contrato de formato do bundle é o de `common-controls` (contrato congelado, commit
`a2cd02c1fc1f06d65f6ee0a6ede75e2855c4001a`), referenciado — nunca copiado. Os fixtures deste
diretório são material de análise preparatória, não evidência de produção.

## O que um bundle pode e não pode fazer

| Situação | Estado esperado | Escopo |
|---|---|---|
| `local_execution: true` | `blocked` | CI estrito |
| Sem SHA de commit do produtor | `blocked` | CI estrito |
| Produtor candidato não mergeado | `blocked` | produção |
| Produtor candidato não mergeado | `accepted_in_fixture_only` | fixture/preparação |
| Produtor mergeado sem release | `blocked` | produção |
| Produtor mergeado sem release | `accepted_in_fixture_only` | fixture/preparação |
| Produtor mergeado sem release como fonte no CI estrito | `blocked` | CI estrito |
| `released` sem tag/version/manifest/hash verificáveis | `blocked` | CI estrito |
| Source commit ≠ `adapter_source_commit` | `blocked` | CI estrito |
| `CTRL-DEP-001` com assertion planejada | `not_satisfied` | CI estrito |
| Release inexistente | `release_eligible: false` | CI estrito |

O invariante inteiro: **evidência de produtor não releaseado pode ser analisada em fixture, nunca
satisfaz controle algum nem entra como evidência de produção.** `CTRL-DEP-001` permanece
`not_satisfied`; `release_eligible` permanece `false`.

## Mutações canônicas (prova de fogo)

| Mutação | Gestos | Asserção |
|---|---|---|
| M36 | `merged_unreleased` com `release_eligible: true` | ADR-032-A12 |
| M37 | `merged_unreleased` como fonte no CI estrito | ADR-032-A13 |
| M38 | `released` sem tag/version/manifest/hash verificáveis | ADR-032-A14, ADR-032-A15 |
| M39 | Source commit ≠ `adapter_source_commit` | ADR-032-A16 |
| M40 | `CTRL-DEP-001` `satisfied` com assertion planejada | ADR-032-A17 |

## Fixtures

- `fixtures/candidate-valid.json` — bundle do adapter mergeado (source commit `f19e5932…`),
  hash canônico determinístico. Uso permitido: fixture/preparação.
- `fixtures/candidate-local.json` — mesmo produtor, `local_execution: true` (status restritos a
  `not_assessed`). Bloqueado no CI estrito.
- `fixtures/candidate-no-commit.json` — produtor sem `suite_commit`. Bloqueado: proveniência sem
  SHA verificável não é proveniência.

Nenhum fixture referencia `main`/`latest` nem contém URL de repositório (ADR-008-A5). Nenhum
fixture declara estado fora dos três controlados — e o estado do produtor, hoje, é
`merged_unreleased`, não `released`.

Fiscalizado por: `harness/schemas/assurance-lock.schema.json`, `harness/schemas/evidence-reference.schema.json`, `ci/validate_metadata.py::main`, `harness/stages.yaml`, `tests/governance/test_assurance_evidence_contract.py`, `tests/governance/test_candidate_adapter_reference.py`
Declarado em: `harness/change-proposals/CP-051-assurance-evidence-candidate.yaml`
Falha como: matriz divergente do schema ou do fecho de situações → `validate_metadata` sai 1; referência em estado proibido ou `released` sem metadados → inexpressível no schema; evidência de produtor não releaseado declarada aceitável em produção ou CI estrito → testes de mordida reprovam.