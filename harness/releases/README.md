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

**Como uma release nasce.** Só pelo job `publicar` de `.github/workflows/release.yml`, por
`workflow_dispatch` com a versão como entrada. A ordem é a decisão inteira (ADR-025):

0. **recusa a entrada malformada** — trim e regex `^v[0-9]+\.[0-9]+\.[0-9]+$`, antes até do
   checkout. Só forma; nada aqui sabe do repositório, e é por isso que roda antes de tê-lo;
1. fixa o commit a validar e recusa tag que já exista no remoto;
2. `validate_all.py`, `pytest tests/governance` e `audit_mutations.py` — *as travas ainda mordem*;
3. `preflight_publicacao`: tag inédita, `HEAD` imóvel desde a validação, manifesto ausente da árvore;
4. emite o manifesto, monta o commit de release e **tagueia localmente**;
5. `--verify-tag` sobre esses objetos, **antes de qualquer push**;
6. `git push` da ref — **sem `--force`**, o que cria e não move.

Qualquer passo vermelho e nenhuma ref nasce. Tag que aponta para commit sem manifesto não é release
parcial — é ausência de release.

**O manifesto vive na árvore do commit taggeado, não na `main`.** `harness/` é caminho protegido e
o ruleset da `main` recusa push direto: um workflow que escrevesse lá faria por fora o que esta
casa exige que se faça por PR. É de lá que `/atualizar-carcaca` o lê — resolvendo a tag, não a
branch.

**O job de auditoria por push de tag continua existindo**, e cobre toda tag que chegue por outro
caminho. Ele **não** roda para a tag que o dispatch cria: ref criada com `GITHUB_TOKEN` não dispara
workflows. Por isso o dispatch verifica a cadeia por conta própria — contar com o push-audit seria
contar com um passo que não executa.

**Como um derivado consome.** `/atualizar-carcaca` resolve a tag, verifica a cadeia e escreve
`target.lock:mold_release`. Ele nunca toca metadado do alvo: a única coisa que ele altera é a
âncora do molde.

Fiscalizado por: `ci/validate_metadata.py::check_release_manifests`, `ci/mold_release.py::verify_chain`
