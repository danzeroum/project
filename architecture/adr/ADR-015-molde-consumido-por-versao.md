# ADR-015 — O molde é consumido por versão, como a régua

**Status:** accepted · **Data:** 2026-08-05 · **Proposta:** CP-021

## Contexto

O ADR-003 já resolveu este problema uma vez, para a régua: a versão da WebQA Suite mora num lugar
só, pinada com `==`, e nenhum outro arquivo a restata. O ADR-008 resolveu de novo, uma camada
adiante: o SHA do alvo mora só em `target.lock`, e é o que impede "este metadado descreve o alvo"
de degradar em silêncio para "descrevia o alvo em algum momento".

Faltava a terceira instância do mesmo problema, e é a que fecha o triângulo: **de qual versão do
molde este derivado nasceu?** Hoje a resposta é nenhuma. A carcaça chega por cópia, num momento
que não fica registrado, e a partir daí as duas árvores divergem sem ponto de comparação. A
pergunta "quanto este derivado está atrasado em relação ao molde?" não é difícil de responder —
ela é *impossível*, porque não existe o dado que a responderia.

## Decisão

**Um derivado declara a versão do molde de que nasceu, e essa declaração é verificável.**

`target.lock` ganha `mold_release = {repository, tag, commit_sha, manifest_path, manifest_sha}`.
O schema exige o bloco quando `kind: derived` e o proíbe quando `kind: mold` — a mesma trava nos
dois sentidos que o par `kind`/`target_sha` já tinha, pela mesma razão: para que não exista
"derivado quase ancorado", estado que dura para sempre porque nenhum fiscal o reprova.

**A raiz de confiança é o manifesto na árvore Git, não a tag.** Tag é ponteiro móvel. Quem pode
escrever reescreve `v1.2.0` para outro commit, e todo derivado que a cita passa a afirmar
procedência sobre um conteúdo que nunca existiu — sem que nenhum fiscal veja diferença. O
manifesto mora em `harness/releases/vX.Y.Z.manifest.json`, **dentro do commit de release**, e o
derivado guarda o `sha256` dos seus bytes. Mover a tag deixa de ser invisível: o manifesto
encontrado no novo destino tem outro hash, e a cadeia quebra alto.

Um manifesto publicado como *release asset* não serviria: asset é editável depois de publicado e a
edição não deixa rastro no histórico. Daí a regra dura — **manifesto fora da árvore, ou tag
apontando para commit sem manifesto, é ausência de release**, nunca release aproximada.

**A autorreferência resolve-se declarando o pai.** Um arquivo não pode conter o hash do commit que
o contém. `release.commit_sha` é portanto o commit do *conteúdo validado* — o primeiro pai do
commit de release —, e o elo que fecha o buraco é a exigência de que o commit de release **não
mude nada além do próprio manifesto**. Sem esse elo, código não validado entraria na versão sob a
bandeira de uma validação que rodou no pai.

**A verificação separa violação de indeterminação.** `verify_chain` é função pura: recebe o
manifesto lido, os bytes, o commit resolvido e os caminhos diffados, e não faz I/O nenhum. Quem
tem a rede é o chamador — o workflow de release e `/atualizar-carcaca`. Um verificador que fizesse
I/O confundiria "a cadeia está quebrada" com "não consegui olhar", e as duas conclusões exigem
reações opostas (princípio (h) do plano). É também o que torna cada elo testável isoladamente, sem
mock de rede.

## Consequências

Um derivado passa a poder responder de que versão nasceu, e a comparação entre derivados de
projetos diferentes passa a significar algo. `/atualizar-carcaca` ganha o mesmo papel que
`/sincronizar` tem para o alvo — medir a distância e transformá-la em trabalho declarado.

O custo: publicar uma versão do molde deixa de ser `git tag`. Passa a exigir um commit de release
que só acrescenta o manifesto, e um workflow que valida antes de aceitar. É deliberado: o atrito
está no lugar certo — publicar —, e não em cada PR.

O que esta decisão **não** faz: ancorar não migra. Um derivado ancorado numa versão nova continua
com os fiscais que tem; adotar o que a versão nova traz é trabalho declarado em change-proposal.

## Fiscal

`ci/validate_metadata.py::check_mold_release` e `::check_release_manifests` cobram a coerência
local; `ci/mold_release.py::verify_chain` executa a cadeia; `.github/workflows/release.yml` a
aplica no momento de publicar. As asserções `ADR-015-A*` em `architecture/adr/index.yaml` provam
que cada uma dessas peças continua existindo e continua mordendo.
