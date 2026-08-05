---
description: Ancora este derivado numa versão publicada do molde, verificando a cadeia inteira antes de escrever.
---

# /atualizar-carcaca

O alvo evolui e `/sincronizar` mede essa distância. O **molde** também evolui, e é essa a distância
que este comando mede. Espelha `/sincronizar` de propósito: mesma forma, mesma disciplina, um andar
acima.

**Pare antes de começar se** `project.yaml:project.kind` não for `derived`. Um molde não nasceu de
molde nenhum, e `target.lock:mold_release` é estruturalmente proibido nele.

## A regra que você não negocia

**Este comando toca `target.lock:mold_release` e mais nada.** Não reingere, não move
`target_sha`, não reescreve `derived_from`, não encosta em `workspace/`. A âncora do molde e a
âncora do alvo são duas perguntas diferentes; um comando que avançasse as duas de uma vez tornaria
impossível saber qual delas causou o vermelho seguinte.

E ele **não avança nada sem cadeia íntegra**. Uma âncora escrita a partir de uma cadeia quebrada é
pior que âncora nenhuma: ela afirma procedência verificada sobre um conteúdo que ninguém verificou.

## Passos

### 1. Descobrir a versão publicada

Liste as tags do repositório do molde declarado em `target.lock:mold_release.repository` (ou, na
primeira ancoragem, o molde de que este repositório nasceu). A tag mais recente `vX.Y.Z` é a
candidata. Se não há tag alguma, **pare**: o molde ainda não publicou versão, e não há o que
consumir.

### 2. Obter o manifesto DA ÁRVORE do commit da tag

O manifesto é `harness/releases/<tag>.manifest.json` **dentro do commit** que a tag aponta — nunca
um asset de release. Asset é editável depois de publicado, e a edição não deixa rastro.

Se a tag aponta para um commit sem esse arquivo na árvore, isto **não** é uma release incompleta.
É ausência de release: relate e pare.

### 3. Verificar a cadeia antes de escrever

Com um clone do molde disponível:

```bash
python ci/mold_release.py --verify-tag <tag>     # rodado DENTRO do clone do molde
```

Os elos, e o que cada um recusa:

1. a tag resolve para um commit concreto;
2. o manifesto está na árvore desse commit;
3. o `sha256` dos bytes do manifesto é o que o lock vai guardar;
4. `release.commit_sha` é o **pai** do commit de release — o conteúdo efetivamente validado;
5. o commit de release **não muda nada além do manifesto** (sem isto, código não validado entra na
   versão sob a bandeira de uma validação que rodou no pai);
6. `validation.result` é `pass`.

Sem acesso ao molde, o estado é **indeterminado**, nunca aprovado: diga que não foi possível
verificar e pare. Ancorar no escuro é a única saída proibida.

### 4. Escrever a âncora

```bash
python ci/mold_release.py --update-lock --manifest <caminho-do-manifesto> --repository <owner/repo>
```

A substituição é cirúrgica e textual: só o bloco `mold_release` muda. Confira com `git diff` —
qualquer linha alterada fora dele é defeito do comando, não resultado esperado.

### 5. Validar

```bash
python ci/validate_all.py
```

## Se a atualização implicar mudanças no derivado

Ancorar numa versão nova do molde **não migra** este repositório para ela. Se a versão nova traz
fiscais, schemas ou etapas que este derivado ainda não tem, isso é trabalho — e trabalho declarado:
abra uma change-proposal de risco `high` (ela muda a carcaça inteira) listando o que muda, do mesmo
modo que `/sincronizar` faz para o alvo. O vermelho que aparecer nesse intervalo é o **mapa** da
migração, não defeito.

## Pronto quando

- [ ] `target.lock:mold_release` existe e a cadeia dos seis elos passou
- [ ] `git diff` mostra alteração **apenas** no bloco `mold_release`
- [ ] `python ci/validate_all.py` sai `0`
- [ ] nenhum `derived_from`, nenhum `target_sha` e nenhum arquivo de `workspace/` foi tocado
