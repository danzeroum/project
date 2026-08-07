# ADR-030 — Uma régua entra por ficha, nunca por código

**Status:** accepted · **Data:** 2026-08-06 · **Proposta:** CP-041

## Contexto

O `WEBQA_CONSUMER_CONTRACT.md` é normativo, versionado e fiscalizado — e cobre **um lado só**.
Ele diz o que este consumidor promete à suíte. Nada dizia o que uma **suíte** precisa entregar
para ser consumível.

A assimetria tinha consequência concreta: os defeitos conhecidos da qa-suite — não publicar
release ancorável, emitir laudo que sai `0` declarando-se inconclusivo — **não tinham onde
aparecer como achado**. E defeito sem lugar onde aparecer é indistinguível de ausência de defeito,
que é a frase que este repositório repete desde o ADR-024.

Havia um segundo problema, de forma. A qa-suite era consumida por gestos cravados um a um: o pin
em `requirements-qa.txt`, o perfil em `tests/qa/config.yaml`, dois passos literais em `qa.yml`, e
a linha `env_denylist_prefix: ["WEBQA_"]` em `harness.yaml`. Nenhum deles sabia ser **instância de
uma classe**. Uma segunda régua exigiria repetir os cinco à mão, e a segunda cópia derivaria da
primeira no primeiro dia em que uma delas mudasse — a mesma deriva que o ADR-003 fecha para a
*versão* e que seguia aberta para o *consumo*.

## Decisão

**Uma régua entra por FICHA (`harness/suites/<nome>.yaml`) e por PIN (o caminho em `pin_source`).
Nunca por código.**

O critério de sucesso é negativo e verificável: **se acrescentar uma régua exigir editar um
fiscal, a padronização não aconteceu.** A ficha `privacy-suite.yaml` nasce junto exatamente para
exercer isso — ela é validada, entra no laudo e cobre `PRIVSUITE_*` na denylist sem uma linha de
código nova.

### As cinco cláusulas

O contrato vive em `harness/suite-contract/contract-v1/SUITE_CONTRACT.md` e enumera o que a régua
deve: pin de fonte única, release com manifesto, envelope de laudo com três estados, fingerprint
de comparabilidade, e autoprova de mordida. Cada uma tem um símbolo que a cobra em
`ci/audit_suites.py`, resolvido por AST — cláusula cujo fiscal não existe é prosa.

### O contrato nasce fechado, e a âncora é o digest

Um contrato de rastreabilidade não-rastreável seria a ironia que este molde já foi até o ADR-015.
`contract-manifest.json` lista cada arquivo do contrato com seu `sha256`. Acrescentar uma sexta
cláusula é a **v2**, nunca uma edição da v1: o schema trava com `minItems: 5` e `maxItems: 5`, sem
o que o contrato mudaria de conteúdo sem mudar de nome e uma ficha `contract_version: v1` passaria
a prometer outra coisa sem que ninguém decidisse nada.

A tag continua sendo a do molde. O digest é o que detecta edição de **um** arquivo do contrato sem
release nova — a mesma razão pela qual `target.lock` guarda `manifest_sha` além da tag.

### O terceiro estado do laudo

`conforme`, `nao_conforme`, **`inconclusivo`**. O terceiro é a cláusula inteira: hoje, suíte
ausente produz `::warning::` e exit `0`, e *"não consegui medir"* sai com a mesma cor de *"medi e
está bom"*. A cor mais barata vence por hábito, e um verde que significa "não olhei" encerra a
investigação com a convicção de quem olhou.

O envelope entra **pelo mecanismo que a casa já usa**: bump de `schema_version` em
`report.schema.json` para `1.3`, com a trava nas duas direções — `1.3` exige `verdict`, e a
presença de `verdict` exige `1.3`. É o idioma de `provenance.schema.json` (`1.1` obriga o bump por
`artifact`, `1.2` por `attestation`), e é o que mantém laudos `1.0` válidos enquanto o gap
`envelope` da qa-suite está aberto — sem que o contrato precise mentir sobre isso.

Ao escrever a cláusula descobriu-se que **`report.schema.json` não validava documento algum**: o
`additionalProperties: false` de `provenance.schema.json`, composto por `$ref` dentro de um
`allOf`, recusava as propriedades que o próprio `report` acrescenta. Ninguém percebeu porque nada
era validado contra ele. Mixin não fecha objeto; quem fecha é o envelope concreto, com
`unevaluatedProperties: false`.

### A denylist deriva do registro

`WEBQA_` sai de `harness.yaml` e nasce de `harness/suites/qa-suite.yaml:env_prefix`; `PRIVSUITE_`
nasce da ficha `planned` **antes de a régua existir**. É a lição do CP-020 aplicada à classe: a
variável de uma régua nova nasce coberta.

A leitura é **fail-closed**. Registro ausente ou ilegível aborta com exit `2` — jamais devolve o
que conseguiu ler. Uma trava que se desliga sozinha quando o registro some não é trava.

### O motor de mutação é compartilhado por pin

`harness/suite-contract/mutation-engine/` recebeu a parte que não sabe nada deste repositório:
derivar o inverso de uma asserção, aplicar, desfazer. Ele importa apenas `json`, `re` e `pathlib`
— a fronteira é de **dados**, e é a condição de possibilidade do segundo consumidor: uma suíte que
precisasse de `harness_lib` para provar as próprias travas receberia meio molde junto com a peça.

`ci/audit_mutations.py` continua sendo o entrypoint, com o que é irredutivelmente daqui: o índice
de ADRs, o fiscal de conformidade, o protocolo `HARNESS_REPO_ROOT`. Os três pontos de invocação
não mudaram, e um teste os vigia — se um deles deixasse de chamar a prova, ficaria verde por não
olhar.

## Consequências

- Uma régua nova custa **uma ficha**, e o fiscal genérico passa a cobrá-la sem edição.
- `release.anchored: false` e pin inexistente continuam sendo respostas legítimas — **declaradas**,
  com gap datado. Gap vencido vira achado bloqueante: não para punir o atraso, mas para forçar
  re-decisão. Prazo que passa sem nada acontecer é prazo decorativo.
- A extração do motor foi provada por invariante: **163 asserções reprovaram suas mutações
  canônicas antes e depois**, com o mesmo conjunto de achados.
- O fiscal **reprova a si mesmo** se qualquer cláusula chegar sem mutação canônica declarada.

## Alternativas rejeitadas

**Um schema irmão para o envelope de três estados.** Duplicaria `result` e `findings`, que é a
segunda cópia que este repositório recusa em toda parte. O `verdict` entrou no envelope existente.

**Copiar o motor de mutação para cada consumidor.** Uma cópia local pode ter um operador
enfraquecido, e a prova passaria a dizer "todas mordem" sem erro nem aviso — o selo falso que
`harness/policies/prova-de-mutacao.md` chama de pior que fiscal nenhum.

**Manter `WEBQA_` em `harness.yaml` e apenas conferir a cobertura.** Mais fraco: cada régua nova
exigiria editar a lista à mão, que é precisamente o gesto que se esquece. A asserção de cobertura
continua existindo, e agora morde contra a reversão da derivação.
