# privacy — outputs

Escreve:
- `governance/ripd.md` — a prosa do julgamento. RIPD completo (8 seções) quando o sistema trata
  dados de titulares; Parecer de Proporcionalidade (4 seções) quando o tratamento é apenas
  incidental. **O tipo não é escolha**: `ci/audit_lgpd.py` o deriva do inventário e reprova se o
  registrado não corresponder.
- `governance/privacy-review.yaml` — o registro tipado: `kind`, `document`, `scope_fingerprint`,
  `issues[]` (com artigo e princípio PbD) e `not_assessed[]`.
- `governance/data-inventory.yaml` — quando o julgamento identificar dado pessoal ainda não
  inventariado, ou uma exclusão de varredura que precise ser declarada com justificativa.
- `harness/reports/privacy-*.md` — relatório técnico legível para o PR (efêmero, gitignored).

O `scope_fingerprint` **nunca** é escrito à mão nem copiado de outro commit:

```bash
python ci/audit_lgpd.py --print-fingerprint
```

Nunca escreve: código de negócio (`src/`), a régua, o pin de dependência, nem os léxicos de
`ci/audit_lgpd.py` (`ci/` é `protected_path`).

Uma revisão que só atualiza o fingerprint sem reler o material é fraude de frescor: o fiscal
passaria a verde sem que julgamento algum tivesse ocorrido. O fingerprint é consequência da
revisão, não o objetivo dela.
