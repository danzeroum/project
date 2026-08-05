# harness/releases — a raiz de confiança das versões do molde

Cada arquivo aqui é o manifesto de uma release: `vX.Y.Z.manifest.json`, validado por
`harness/schemas/release-manifest.schema.json`.

**Por que na árvore Git e não como release asset.** Um asset é editável depois de publicado e a
edição não deixa rastro no histórico. Um arquivo na árvore do commit de release é endereçado por
hash junto com todo o resto: mover a tag muda o manifesto que se encontra no destino, e o
`manifest_sha` guardado no derivado deixa de conferir. É o que transforma "a tag foi movida" de
evento invisível em falha de CI.

**O manifesto declara o pai, e isso é deliberado.** `release.commit_sha` é o commit cujo conteúdo
foi validado — o primeiro pai do commit de release. Um arquivo não pode conter o hash do commit
que o contém; declarar o pai é a formulação honesta. O elo que fecha o buraco é
`ci/mold_release.py::verify_chain`, que exige que o commit de release **não mude nada além deste
manifesto**: sem ele, código não validado entraria na versão sob a bandeira de uma validação que
rodou no pai.

**Como uma release nasce.** Só por `.github/workflows/release.yml`, em push de tag `vX.Y.Z`. O
workflow roda a validação total, verifica a cadeia inteira e falha se qualquer elo estiver rompido.
Tag que aponta para commit sem manifesto não é release parcial — é ausência de release.

**Como um derivado consome.** `/atualizar-carcaca` resolve a tag, verifica a cadeia e escreve
`target.lock:mold_release`. Ele nunca toca metadado do alvo: a única coisa que ele altera é a
âncora do molde.

Fiscalizado por: `ci/validate_metadata.py::check_release_manifests`, `ci/mold_release.py::verify_chain`
