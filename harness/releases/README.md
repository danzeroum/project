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

**O registro nasce do commit validado.** Publicada a ref, o workflow volta ao commit **validado**,
acrescenta a linha `release` ao ledger e empurra para `release/ledger-vX.Y.Z`. O registro não
precisa *descender* do commit que ele registra — precisa **citá-lo**, e `commit_sha` já faz isso.
Confundir as duas coisas custou um PR manual ao fechar a v1.0.0: como filho do commit de release, a
branch de evidência carregava o manifesto junto e não mergeava. Nascendo do validado, ela é a `main`
mais um commit que muda um arquivo — e o PR é direto.

**O manifesto vive na árvore do commit taggeado, não na `main`.** `harness/` é caminho protegido e
o ruleset da `main` recusa push direto: um workflow que escrevesse lá faria por fora o que esta
casa exige que se faça por PR. É de lá que `/atualizar-carcaca` o lê — resolvendo a tag, não a
branch.

**O job de auditoria por push de tag continua existindo**, e cobre toda tag que chegue por outro
caminho. Ele **não** roda para a tag que o dispatch cria: ref criada com `GITHUB_TOKEN` não dispara
workflows. Por isso o dispatch verifica a cadeia por conta própria — contar com o push-audit seria
contar com um passo que não executa.

**O que o auditar valida, e onde** (ADR-026). Recusa tag movida, verifica a cadeia **enquanto a tag
está montada** — `--verify-tag` lê o manifesto do disco — e só então volta ao **pai** para rodar
`validate_all.py`, os testes e a prova de mutação. A árvore taggeada não se valida por
`validate_all`: ela se valida pela cadeia, porque o manifesto descreve a validação do pai e o elo
*"nada além do manifesto"* é o que a transporta.

**O manifesto não carrega URL de repositório.** `run_url` saiu de `build_manifest` e do CLI: não é
proibido, é inexpressável. `repository` + `run_id` reconstroem a URL. O schema segue aceitando o
campo para que o manifesto da v1.0.0 — que o carrega — continue válido como registro histórico.

**Como um derivado consome.** `/atualizar-carcaca` resolve a tag, verifica a cadeia e escreve
`target.lock:mold_release`. Ele nunca toca metadado do alvo: a única coisa que ele altera é a
âncora do molde.

Fiscalizado por: `ci/validate_metadata.py::check_release_manifests`, `ci/mold_release.py::verify_chain`
