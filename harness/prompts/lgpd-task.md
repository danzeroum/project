# Tarefa: revisão de privacidade (agente `privacy`)

## Quando esta tarefa é disparada

Sempre que `ci/audit_lgpd.py` acusar `judgment_stale`, `JUDGMENT-KIND` ou
`JUDGMENT-DOC-INCOMPLETE` — ou seja, quando o escopo mudou e o julgamento anterior deixou de
falar deste sistema. Também a pedido, antes de um release ou de uma mudança que toque dado
pessoal.

## Passos permitidos

1. **Ler o laudo determinístico primeiro.** `harness/reports/lgpd-audit.json` já traz o que a
   máquina encontrou. Repetir esses achados como se fossem descoberta do julgamento infla o
   relatório e esconde o que só o julgamento acha.
2. **Delimitar o escopo real.** Listar o que foi de fato avaliado. `harness/stages.yaml` dá a
   superfície e a `privacy_lens.question` de cada etapa — o julgamento percorre as etapas, não
   um recorte escolhido na hora.
3. **Executar a skill `/revisao-lgpd`** sobre o repositório inteiro, percorrendo todas as
   categorias aplicáveis do checklist.
4. **Classificar cada issue** com severidade P0–P3, artigo da LGPD e princípio PbD violado.
5. **Escrever os dois artefatos**, nesta ordem: `governance/ripd.md` (prosa, no tipo que o
   inventário exige) e `governance/privacy-review.yaml` (registro tipado).
6. **Atualizar o inventário** se o julgamento identificou dado pessoal fora dele.
7. **Recalcular o fingerprint por último:** `python ci/audit_lgpd.py --print-fingerprint`.
8. **Fechar verde:** `python ci/validate_all.py`.

## Ações proibidas

- Disparar `passive`, `load` ou `active_discovery`. O julgamento é sobre o repositório.
- Editar os léxicos de `ci/audit_lgpd.py`. Suprimir é declarar em
  `data-inventory.yaml:scan.exclusions` com justificativa — apagar termo desliga a busca em
  silêncio, e `ci/` é `protected_path`.
- Escrever "sem achados" numa categoria que não foi avaliada. Vai para `not_assessed`.
- Atualizar o `scope_fingerprint` sem refazer a revisão. Isso é fraude de frescor: o fiscal
  ficaria verde sem julgamento algum. O fingerprint é consequência da revisão, não o objetivo.
- Afirmar violação sem citar artigo, ou mitigação sem verificar a premissa. Antes de apontar
  "retenção indefinida", conferir se o arquivo de fato acumula; antes de citar um pipeline como
  mitigação, conferir que ele existe.

## Entregável

- `governance/ripd.md` — 8 seções (RIPD) ou 4 seções (Parecer), conforme o inventário exigir.
- `governance/privacy-review.yaml` — `kind`, `document`, `scope_fingerprint`, `issues[]`,
  `not_assessed[]`. Issue P0/P1 exige um `RISK-*` do registro (trava de schema).
- `harness/reports/privacy-*.md` — relatório técnico legível para o PR.
- Resumo executivo de 3 a 5 linhas: contagem por severidade e os P0 nominalmente.
