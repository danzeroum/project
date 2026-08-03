# Política: como a versão do padrão sobe

- **Projetos declaram versão exata** (`==`), nunca faixa. A superfície do que a suíte procura é
  dado de segurança; ela não deve mudar sozinha entre dois runs.
- **Subir de versão é decisão versionada**, num PR do projeto, com o laudo anterior e o novo lado
  a lado. A mudança de superfície fica visível na revisão.
- **A harness pode _propor_ a subida**; nunca executá-la sozinha.

Ao subir:
1. Editar o pin em `requirements-qa.txt` (`webqa-suite==<nova>`).
2. Atualizar `standard_version` em `tests/qa/config.yaml` para o mesmo valor (o contrato cruza os
   dois).
3. Anexar ao PR o laudo anterior e o novo, para inspeção da diferença de superfície.

---

Fiscalizado por: `.github/workflows/qa.yml` (recomputa a fingerprint da régua a cada run);
revisão humana do PR com os dois laudos.
Fiscalizado por (contrato): `WEBQA_CONSUMER_CONTRACT.md` §7 — pin exato, sem faixa; `standard_version`
deve casar com o pin.
Falha como: pin não-`==` ou `standard_version` divergente ⇒ `CONFIG_INVALID` (40).
