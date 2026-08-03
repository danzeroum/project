# Política: todo laudo carimba a régua

A suíte pode ser agnóstica a projeto e a versão de harness. **O laudo nunca é.**

Suponha:
- Projeto A rodou a suíte v1.2, que procurava 5 tipos de arquivo exposto → *0 achados*
- Projeto B rodou a suíte v1.6, que procura 40 tipos → *0 achados*

Os dois laudos dizem a mesma frase e afirmam coisas diferentes. Colocá-los lado a lado numa
planilha produz um número falso, sem que ninguém perceba.

## Requisito

Todo artefato produzido carrega a procedência do padrão (schema em
`../schemas/provenance.schema.json`): `schema_version`, `standard{name, version, commit,
sensitive_paths_hash}`, `consumer_project{repository, commit}`, `execution{run_id, mode,
network_used, active_gates, runner_kind}`.

O `sensitive_paths_hash` fecha o buraco de `webqa.md`: se dois laudos têm a mesma versão do padrão
e hashes de lista diferentes, alguém editou a lista. Isso deixa de ser invisível.

A agregação **recusa** comparar quando `standard.version`, `standard.commit`,
`sensitive_paths_hash` ou `schema_version` são incompatíveis. "Não comparável" é um resultado
válido — muito melhor que um dashboard aparentemente preciso e enganoso.

---

Fiscalizado por: `harness/schemas/provenance.schema.json`,
`harness/schemas/report.schema.json` (procedência obrigatória, `additionalProperties: false`).
Fiscalizado por: (na suíte) construção do laudo carimba versão/commit/hash; agregador recusa
réguas incompatíveis (`WEBQA_CONSUMER_CONTRACT.md` §7).
Falha como: laudo sem procedência ⇒ `PROVENANCE_INVALID` (30); réguas incompatíveis ⇒
`NOT_COMPARABLE` (31).
