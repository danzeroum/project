# harness/policies — índice, não a política

Estes arquivos são um **índice**, não a política em si. A política em markdown não morde: é a
diferença entre uma placa de "proibido fumar" e um detector ligado ao alarme. A placa depende de
alguém ler e obedecer.

Cada arquivo aqui descreve uma regra e termina com um apontamento `Fiscalizado por:` para o local
onde ela é **efetivamente** aplicada — um gate da suíte externa, um passo do CI, ou um schema.

> **Uma entrada sem apontamento `Fiscalizado por:` resolvível é um lembrete, nunca uma garantia.**

Índice:

| Política | Regra | Fiscal |
|---|---|---|
| [`webqa.md`](webqa.md) | declarar-não-copiar + pin exato | CI (recusa de vendored) + gates da suíte |
| [`execution-modes.md`](execution-modes.md) | matriz modo × runner-kind | jobs segregados do CI |
| [`env-hygiene.md`](env-hygiene.md) | allowlist/denylist + fail-closed | bloco `env:` do `qa.yml` |
| [`provenance.md`](provenance.md) | carimbo + recusa de comparação | schemas + suíte |
| [`dependency-updates.md`](dependency-updates.md) | como o pin sobe | CI + PR do projeto |
| [`change-proposals.md`](change-proposals.md) | proposta afeta só IDs reais; risco alto exige aval | schema + `ci/validate_metadata.py` |
| [`conformance.md`](conformance.md) | ADR declara asserção executável; toda etapa tem fiscal | `ci/audit_governance.py` + schema |
| [`lgpd.md`](lgpd.md) | inventário de dado pessoal; julgamento existe e não venceu | `ci/audit_lgpd.py` + schema |
| [`ancoragem-do-molde.md`](ancoragem-do-molde.md) | derivado declara de qual versão do molde nasceu; a âncora é o hash do manifesto | `ci/mold_release.py` + `ci/validate_metadata.py` + workflow de release |
