# Evidência do produtor PSE — análise em fixture, aprovação em lugar nenhum

A PR #2 da pse-suite foi mergeada em 17/08/2026 20:23:21 UTC, e não há release da PSE: não
existe tag `v0.4.0`, manifesto de release ou pin versionado. Enquanto o produtor for
**`merged_unreleased`** (ou `candidate_not_merged`), a evidência que ele produz tem um lugar
permitido — fixture e preparação — e dois lugares proibidos: CI estrito e produção.

A fronteira inteira é declarada no `harness/suite-contract/evidence-bundle/compatibility-matrix.yaml`
(o *assurance lock*), e o schema dela é fechado nos dois sentidos:

- `candidate_reference.state` só admite três valores (`candidate_not_merged`,
  `merged_unreleased`, `released`), `release_eligible` é `const: false` para os dois primeiros e
  `released` exige tag, versão, commit, manifesto e hash de artefato verificáveis
  (`harness/schemas/evidence-reference.schema.json`). **Não existe forma de declarar um produtor
  fora desses estados** — merge no main não vira release por esquecimento, porque
  `released` sem metadados é inexpressível.
- O fecho de situações é completo por `minItems`/`maxItems` (11 situações): acrescentar uma
  décima segunda é edição de contrato (nova versão, novo ADR), nunca um enriquecimento silencioso
  da matriz.

Regras:

1. **Bundle com `local_execution: true` não entra em CI estrito** — estado esperado `blocked`.
2. **Produtor candidato não mergeado é `blocked` para produção** — aceito somente em
   fixture/preparação.
3. **Produtor mergeado sem release é `blocked` para produção e para fonte no CI estrito** —
   aceito somente em fixture/preparação (integração preparatória e validação local controlada).
4. **Bundle sem SHA de commit do produtor é `blocked`** — proveniência sem SHA verificável não é
   proveniência.
5. **`released` sem tag/version/manifest/hash verificáveis é `blocked`** — o estado só existe
   com os metadados; sem eles, é inexpressível no schema e bloqueado na matriz.
6. **Source commit diferente do `adapter_source_commit` declarado é `blocked`** — um bundle que
   não saiu do adapter mergeado não é evidência do produtor declarado.
7. **Assertion planejada sai `not_assessed`** — nunca `passed` por ser de produtor mergeado.
8. **`CTRL-DEP-001` permanece `not_satisfied`** — evidência de produtor não releaseado não
   satisfaz controle.
9. **Sem release, `release_eligible` permanece `false`** — nada neste repositório depende de
   release inexistente.

O que esta política **não** faz: instalar PSE, executar `pse evidence-bundle` em CI, abrir
tráfego de rede, criar `requirements-pse.txt` ativo, ou registrar suite ativa da PSE em
`harness/suites/`. O produtor segue apenas referência — `merged_unreleased`, `release_eligible:
false`, até existir tag `v0.4.0` verificável (aí, e só aí, o estado muda para `released`, com ADR
novo).

Fiscalizado por: `ci/validate_metadata.py::main`, `harness/schemas/assurance-lock.schema.json`, `harness/schemas/evidence-reference.schema.json`, `harness/stages.yaml`, `tests/governance/test_assurance_evidence_contract.py`, `tests/governance/test_candidate_adapter_reference.py`
Declarado em: `harness/change-proposals/CP-051-assurance-evidence-candidate.yaml`
Falha como: matriz fora do schema ou com situação a mais/menos → `validate_metadata` sai 1; referência em estado proibido ou `released` sem metadados → inexpressível no schema; teste de mordida que injeta estado proibido e vê verde → o teste reprova (a trava não morde).