# Contrato de Régua — uma suíte entra por ficha, e o contrato diz o que ela deve

Duas frases separam esta política de tudo que já existia aqui:

> O `WEBQA_CONSUMER_CONTRACT.md` diz o que **este consumidor** promete à suíte.
> Este contrato diz o que **a suíte** precisa entregar para ser consumível.

A assimetria não era acadêmica. Enquanto só um lado estava escrito, os defeitos conhecidos da
qa-suite — não publicar release ancorável, emitir laudo que sai `0` declarando-se inconclusivo —
**não tinham onde aparecer como achado**. E defeito sem lugar onde aparecer é indistinguível de
ausência de defeito.

## A regra

Uma régua entra por **ficha** (`harness/suites/<nome>.yaml`) e por **pin** (o caminho declarado em
`pin_source`). Nunca por código.

O critério é negativo e verificável: **se acrescentar uma régua exigir editar um fiscal, a
padronização não aconteceu** — e o achado é sobre o fiscal, não sobre a régua. A ficha
`privacy-suite.yaml` existe para exercer isso: uma régua que ainda não existe já é validada, já
aparece no laudo e já cobre `PRIVSUITE_*` na denylist, sem uma linha de código nova.

## O que o contrato cobra

Cinco cláusulas, cada uma com um símbolo que a cobra em `ci/audit_suites.py`, resolvido por AST:
pin de fonte única, release com manifesto, envelope de laudo com três estados, fingerprint de
comparabilidade, e autoprova de mordida. O texto normativo é
`harness/suite-contract/contract-v1/SUITE_CONTRACT.md`.

## Gap é dívida com data, e vencido ele acusa

`release.anchored: false` e `pin_source` inexistente são respostas **legítimas** — quando
declaradas. Cada uma exige um `gap` apontando a cláusula, com `declared_at` e `due`.

Vencido o prazo, o gap vira achado bloqueante. Não para punir o atraso: para forçar
**re-decisão**. Ou a régua cumpriu a cláusula, ou alguém renegocia o prazo com nome e data. Prazo
que passa sem nada acontecer é prazo decorativo, e uma dívida que envelhece calada é
indistinguível de conformidade.

## Por que a v1 é fechada por digest

Um contrato de rastreabilidade não-rastreável seria a ironia que este molde já foi até o ADR-015.
`contract-manifest.json` lista cada arquivo do contrato com seu `sha256`. Acrescentar uma sexta
cláusula é a **v2**, travada por `minItems`/`maxItems` iguais a 5 — sem isso o contrato mudaria de
conteúdo sem mudar de nome, e uma ficha `contract_version: v1` passaria a prometer outra coisa.

A tag continua sendo a do molde: o contrato viaja dentro da release `vX.Y.Z`, cujo
`artifact_digest` cobre a árvore inteira. O que o manifesto acrescenta é detectar a edição de
**um** arquivo do contrato sem release nova.

## A denylist deriva do registro

`WEBQA_` saiu de `harness.yaml`. Ele nasce de `harness/suites/qa-suite.yaml:env_prefix`, e
`PRIVSUITE_` nasce da ficha `planned` **antes de a régua existir**. É a lição do CP-020 aplicada à
classe: a variável de uma régua nova nasce coberta, sem que ninguém precise lembrar de uma segunda
lista.

A leitura é **fail-closed**: registro ausente ou ficha ilegível aborta com exit `2`, jamais devolve
o que conseguiu ler. Uma trava que se desliga sozinha quando o registro some não é trava.

## O motor de mutação, compartilhado por pin

`harness/suite-contract/mutation-engine/` importa apenas `json`, `re` e `pathlib`. A fronteira é de
**dados** — ele recebe a asserção e a raiz, e devolve o estado para desfazer — e é isso que permite
a um segundo consumidor usá-lo sem receber meio molde junto. `harness_lib` fica do lado do molde,
adaptando.

Ele é **consumido por pin**, com `sha256` no manifesto, nunca copiado. Uma cópia local pode ter um
operador enfraquecido, e a prova passaria a dizer "todas mordem" sem erro nem aviso — o selo falso
que `prova-de-mutacao.md` chama de pior que fiscal nenhum, porque encerra a investigação.

## O que a extração precisou provar

Não bastava o molde continuar verde. Foram três provas, e a terceira é a que justifica a extração:

1. **invariante** — as asserções bloqueantes reprovaram suas mutações canônicas antes e depois da
   extração, com o mesmo conjunto de achados;
2. **os três pontos de invocação** (`governance.yml`, e duas vezes `release.yml`) continuam
   chamando a prova — um ponto que deixasse de chamá-la ficaria verde por **não olhar**, que é o
   pior verde deste repositório;
3. **os dois consumidores** — um operador enfraquecido no motor reprova no molde (`nao_morde`) e
   reprova em quem o consome por pin (`DIGEST-DIVERGENTE`). Provar só o primeiro mostraria que a
   extração não quebrou nada, sem mostrar que ela **serve** a quem a motivou.

Fiscalizado por: `ci/audit_suites.py`, `harness/schemas/suite-registry.schema.json`, `harness/schemas/suite-contract-manifest.schema.json`, `harness/schemas/report.schema.json`, `ci/env_guard.py`
Declarado em: `harness/change-proposals/CP-041-contrato-de-regua.yaml`, `architecture/adr/ADR-030-a-regua-entra-por-ficha.md`
Falha como: ficha sem `env_prefix` ou com `contract_version` inexistente ⇒ exit 1 no fiscal de metadados; gap vencido, cláusula violada ou digest do contrato divergente ⇒ exit 1 em `ci/audit_suites.py`; registro ausente ⇒ exit 2.
