#!/usr/bin/env python3
"""Raiz de confiança do molde — construir, verificar e consumir uma release por versão.

Este arquivo tem uma divisão interna que é a decisão inteira do CP-021, e vale enunciá-la antes
do código: `verify_chain` é FUNÇÃO PURA. Ela não abre socket, não chama git, não lê o disco. Tudo
que ela precisa saber chega como argumento — o manifesto já lido, os bytes já lidos, o commit já
resolvido, os caminhos já diffados. Quem tem a rede é o chamador: o workflow de release (que tem
o clone) e `/atualizar-carcaca` (que tem a sessão). O motivo é o princípio (h) do plano aplicado
antes de existir violação: um verificador que faz I/O confunde "a cadeia está quebrada" com "não
consegui olhar", e as duas conclusões exigem reações opostas. Também é o que torna cada elo
testável isoladamente, sem mock de rede e sem repositório de mentira.

Uso:
  python ci/mold_release.py --emit --repository O/R --tag vX.Y.Z --commit SHA \\
      --run-id N [--artifact-digest sha256:...]                 # escreve o manifesto
  python ci/mold_release.py --verify-tag vX.Y.Z                 # cadeia completa, via git local
  python ci/mold_release.py --preflight vX.Y.Z --validado SHA   # pode publicar AGORA?
  python ci/mold_release.py --update-lock --manifest CAMINHO --repository O/R
Saída: 0 conforme · 1 cadeia quebrada · 2 não foi possível verificar (indeterminação).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import harness_lib as hl

RELEASES_DIR = "harness/releases"
LOCK = "target.lock"
VALIDATION_COMMAND = "python ci/validate_all.py"

# Indeterminação: nem conforme nem violação. Ver princípio (h) — colapsar os dois faria "estou
# offline" e "a tag foi movida" produzirem a mesma cor, e a cor mais barata venceria por hábito.
EXIT_UNVERIFIABLE = 2


# --------------------------------------------------------------------------------------
# Forma canônica — o hash só significa algo se os bytes forem reprodutíveis
# --------------------------------------------------------------------------------------

def manifest_path_for(tag: str) -> str:
    """O caminho é DERIVADO da tag, nunca escolhido. Um manifesto cujo nome não deriva da tag
    permitiria duas releases apontando para o mesmo arquivo — e a segunda venceria em silêncio."""
    return f"{RELEASES_DIR}/{tag}.manifest.json"


def canonical_bytes(manifest: dict) -> bytes:
    """A serialização é parte do contrato: `manifest_sha` compara BYTES, e bytes dependem de
    indentação, ordem e encoding. Fixar isso aqui é o que impede 'o mesmo manifesto' de ter dois
    hashes conforme quem o escreveu."""
    return (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def manifest_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_curto(h: str, outro: str, minimo: int = 12) -> str:
    """Prefixo que INCLUI o primeiro dígito divergente. Nunca dois prefixos iguais sob 'não confere'.

    Achado do primeiro derivado a consumir a v1.0.0 (CP-038). O corte fixo em 12 produzia, quando a
    alteração estava além da posição 12:

        manifest_sha não confere: o lock espera 8d5986b6ad3c e os bytes (...) produzem 8d5986b6ad3c

    Dois prefixos idênticos sob a palavra "não confere" — quem lê perde tempo achando que o fiscal
    está errado. E o caso não é raro: é exatamente o de quem adultera com cuidado, e é o que o teste
    de borda desta casa exercita.

    Truncar continua certo (64 caracteres duas vezes numa linha não se lê). O que muda é ONDE se
    corta: no ponto que carrega a informação, não num número redondo.
    """
    i = next((k for k, (a, b) in enumerate(zip(h, outro)) if a != b), None)
    if i is None:
        return h[:minimo]
    corte = max(minimo, i + 1)
    return h[:corte] + ("…" if corte < len(h) else "")


def build_manifest(*, repository: str, tag: str, commit_sha: str, run_id: str,
                   artifact_digest: str, released_at: str | None = None) -> dict:
    """O manifesto NÃO carrega URL de repositório (CP-034).

    Não é 'proibido escrever': é que não existe mais caminho que produza o campo — mesma
    formulação da CP-026, e pela mesma razão, porque proibição depende de alguém lembrar. O
    ADR-008-A5 reprova URL de repositório em `harness/`, e um manifesto que a carregasse
    tornaria a própria árvore publicada indefensável sob a régua da casa.

    O dado não se perde: `repository` + `run_id` reconstroem a URL. O SCHEMA continua
    aceitando o campo, de propósito — o manifesto da v1.0.0 é registro histórico e precisa
    seguir válido sob o schema que o governa. Registro que se invalida quando a regra muda
    deixa de ser registro.
    """
    release = {
        "repository": repository,
        "tag": tag,
        "commit_sha": commit_sha,
        "released_at": released_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validation": {"command": VALIDATION_COMMAND, "result": "pass", "run_id": str(run_id)},
        "artifact_digest": artifact_digest,
    }
    return {
        "schema_version": "1.0",
        "metadata_version": "1.0",
        "source_of_truth": True,
        "generated_from": None,
        "release": release,
    }


# --------------------------------------------------------------------------------------
# A cadeia — função pura, um elo por bloco, cada elo com violação própria
# --------------------------------------------------------------------------------------

def verify_chain(*, lock: dict, manifest: dict, manifest_bytes: bytes,
                 tag_commit_sha: str, parent_sha: str | None,
                 changed_paths: list[str] | None) -> list[str]:
    """Devolve a lista de elos rompidos. Lista vazia = cadeia íntegra.

    Devolve LISTA, não booleano, pelo mesmo motivo que o fiscal de metadados acumula em err():
    quem está consertando precisa ver os cinco problemas de uma vez, não descobrir o quinto depois
    de quatro rodadas. E cada elo tem mensagem própria porque "cadeia inválida" não diz a ninguém
    se a tag foi movida, se o hash não bate ou se o lock aponta para outro commit.
    """
    violations: list[str] = []
    rel = (manifest or {}).get("release") or {}
    mr = (lock or {}).get("mold_release") or {}

    if not mr:
        return ["o lock não declara mold_release — um derivado sem âncora de molde não foi "
                "ancorado em versão alguma"]

    tag = mr.get("tag")

    # Elo 4 — manifesto e consumidor concordam sobre QUAL conteúdo foi validado.
    if mr.get("commit_sha") != rel.get("commit_sha"):
        violations.append(
            f"commit_sha divergente: o lock declara {str(mr.get('commit_sha'))[:12]} e o manifesto "
            f"declara {str(rel.get('commit_sha'))[:12]} — os dois não falam da mesma árvore")

    if mr.get("tag") != rel.get("tag"):
        violations.append(
            f"tag divergente: o lock declara {mr.get('tag')!r} e o manifesto declara "
            f"{rel.get('tag')!r}")

    if mr.get("repository") != rel.get("repository"):
        violations.append(
            f"repositório divergente: o lock declara {mr.get('repository')!r} e o manifesto "
            f"declara {rel.get('repository')!r}")

    # Elo 3 — o hash confere. É o elo que torna a tag móvel detectável: mover a tag muda o
    # manifesto encontrado no destino, e bytes diferentes têm hash diferente.
    encontrado = manifest_sha(manifest_bytes)
    if mr.get("manifest_sha") != encontrado:
        violations.append(
            f"manifest_sha não confere: o lock espera {_hash_curto(str(mr.get('manifest_sha')), encontrado)} "
            f"e os bytes do manifesto em {mr.get('manifest_path')} produzem "
            f"{_hash_curto(encontrado, str(mr.get('manifest_sha')))} — ou a tag foi "
            f"movida, ou o manifesto foi reescrito depois de consumido")

    if tag and mr.get("manifest_path") != manifest_path_for(tag):
        violations.append(
            f"manifest_path {mr.get('manifest_path')!r} não é o derivado da tag {tag!r} "
            f"({manifest_path_for(tag)}) — caminho escolhido à mão permite duas releases no mesmo "
            f"arquivo")

    # Elo 1 e 2 — a tag resolve para um commit, e o manifesto declara o PAI desse commit como o
    # conteúdo validado. parent_sha None = o chamador não conseguiu resolver: indeterminação, que
    # é do chamador tratar, não violação a inventar aqui.
    if parent_sha is not None and rel.get("commit_sha") != parent_sha:
        violations.append(
            f"o manifesto de {tag} declara ter validado {str(rel.get('commit_sha'))[:12]}, mas o "
            f"commit de release {tag_commit_sha[:12]} tem como pai {parent_sha[:12]} — o manifesto "
            f"descreve uma árvore que não é a que está sendo publicada")

    # Elo 5 — o commit de release não acrescenta nada além do próprio manifesto.
    if changed_paths is not None:
        esperado = manifest_path_for(tag) if tag else None
        intrusos = sorted(p for p in changed_paths if p != esperado)
        if intrusos:
            violations.append(
                f"o commit de release muda {len(intrusos)} caminho(s) além do manifesto "
                f"({', '.join(intrusos[:5])}) — o que foi validado é o pai, então tudo que o commit "
                f"de release acrescenta entra na versão SEM ter passado pela validação que ela declara")

    if rel.get("validation", {}).get("result") != "pass":
        violations.append("o manifesto não declara validação 'pass' — release não nasce de commit "
                          "não validado")

    return violations


TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


def preflight_publicacao(*, tag: str, tags_remotas: list[str], head_sha: str,
                         validado_sha: str, manifesto_na_arvore: bool) -> list[str]:
    """As pré-condições da publicação — o LIMITE DE MAIOR RISCO do caminho de release.

    A cadeia (`verify_chain`) responde "o que já foi publicado confere?". Esta função responde a
    pergunta anterior, e ela é de outra natureza: "publicar AGORA é legítimo?". Separá-las importa
    porque a segunda tem uma janela — entre o commit que a validação aprovou e o instante em que a
    ref nasce, o mundo pode mudar. Se mudar e ninguém olhar, a tag passa a certificar uma árvore
    que nenhuma validação viu, com o carimbo de uma que viu outra.

    Três negativas, e cada uma fecha um modo de falha distinto:

      TAG PREEXISTENTE. Publicar por cima é mover a âncora, e âncora móvel faz todo derivado que a
      cita afirmar procedência sobre conteúdo que nunca existiu. O `git push` sem `--force` já
      recusa — isto é a recusa ANTES do trabalho, para que a falha chegue em segundos e não depois
      da prova de mutação.

      HEAD MOVIDO. `validado_sha` é o commit em que a validação total rodou; `head_sha` é o que
      está prestes a virar pai do commit de release. Diferentes ⇒ a validação não fala do que vai
      ser publicado. É a janela inteira, num `!=`.

      MANIFESTO JÁ NA ÁRVORE. Se o commit validado já contém o manifesto desta tag, o commit de
      release não teria o que acrescentar — e o elo 5 de `verify_chain` (o commit de release não
      muda nada além do manifesto) passaria por vacuidade em vez de por verificação.

    Pura pela mesma razão de `verify_chain`: quem tem o git e a rede é o chamador. "A publicação é
    ilegítima" e "não consegui olhar" pedem reações opostas (princípio (h)).
    """
    v: list[str] = []

    if not TAG_RE.match(tag or ""):
        v.append(f"a tag {tag!r} não tem a forma vX.Y.Z — o caminho do manifesto é DERIVADO da "
                 f"tag, e uma tag de forma livre produz um caminho que nenhum fiscal prevê")

    if tag in tags_remotas:
        v.append(f"a tag {tag} já existe no remoto — publicar por cima seria mover a âncora, e "
                 f"todo derivado que a cita passaria a afirmar ter nascido de algo que já não está "
                 f"lá. Uma versão nova recebe um número novo")

    if head_sha != validado_sha:
        v.append(f"o HEAD mudou entre a validação e a criação da ref: validou-se "
                 f"{validado_sha[:12]} e o pai do commit de release seria {head_sha[:12]} — a tag "
                 f"certificaria uma árvore que nenhuma validação olhou")

    if manifesto_na_arvore:
        v.append(f"{manifest_path_for(tag)} já está na árvore do commit validado — o commit de "
                 f"release não teria o que acrescentar, e o elo que exige 'nada além do manifesto' "
                 f"passaria por vacuidade")

    return v


# --------------------------------------------------------------------------------------
# Consumo — o lock ganha a âncora, e SÓ ela
# --------------------------------------------------------------------------------------

def lock_block(*, repository: str, tag: str, commit_sha: str, manifest_bytes: bytes) -> dict:
    return {
        "repository": repository,
        "tag": tag,
        "commit_sha": commit_sha,
        "manifest_path": manifest_path_for(tag),
        "manifest_sha": manifest_sha(manifest_bytes),
    }


def update_lock(lock_path: Path, block: dict) -> None:
    """Reescreve APENAS mold_release no target.lock, preservando todo o resto.

    Reescrever o arquivo inteiro a partir do dict carregado apagaria comentários e reordenaria
    chaves — e um comando que promete 'só atualizo a âncora' e devolve um diff de arquivo inteiro
    não é auditável por ninguém. Por isso a substituição é textual e cirúrgica: o bloco é trocado
    onde já existe, ou acrescentado ao fim, e nenhuma outra linha é tocada.
    """
    import yaml

    texto = lock_path.read_text(encoding="utf-8")
    novo = yaml.safe_dump({"mold_release": block}, allow_unicode=True, sort_keys=False).rstrip("\n")

    linhas = texto.splitlines()
    inicio = next((i for i, l in enumerate(linhas) if l.startswith("mold_release:")), None)
    if inicio is None:
        return lock_path.write_text(texto.rstrip("\n") + "\n\n" + novo + "\n", encoding="utf-8")

    fim = inicio + 1
    while fim < len(linhas) and (not linhas[fim].strip() or linhas[fim].startswith((" ", "\t"))):
        fim += 1
    lock_path.write_text("\n".join(linhas[:inicio] + novo.splitlines() + linhas[fim:]) + "\n",
                         encoding="utf-8")


# --------------------------------------------------------------------------------------
# CLI — a camada que tem I/O, e por isso a que traduz "não consegui" em exit 2
# --------------------------------------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=hl.REPO, capture_output=True, text=True,
                          check=True).stdout.strip()


def _cmd_emit(args) -> int:
    manifest = build_manifest(
        repository=args.repository, tag=args.tag, commit_sha=args.commit,
        run_id=args.run_id, artifact_digest=args.artifact_digest,
        released_at=args.released_at,
    )
    problemas = hl.schema_errors(manifest_path_for(args.tag), "release-manifest.schema.json", manifest)
    if problemas:
        for p in problemas:
            print(f"✗ {p}", file=sys.stderr)
        return 1
    destino = hl.REPO / manifest_path_for(args.tag)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(canonical_bytes(manifest))
    print(f"✓ manifesto escrito: {manifest_path_for(args.tag)} "
          f"(sha256 {manifest_sha(canonical_bytes(manifest))[:12]})")
    return 0


def _cmd_verify_tag(args) -> int:
    tag = args.tag
    try:
        commit = _git("rev-list", "-n", "1", tag)
        pais = _git("rev-list", "--parents", "-n", "1", commit).split()
        parent = pais[1] if len(pais) > 1 else None
        mudados = _git("diff", "--name-only", f"{parent}..{commit}").splitlines() if parent else None
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"• cadeia da release {tag}: não foi possível resolver pelo git ({exc}). "
              f"Indeterminação, nunca aprovação.", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    caminho = hl.REPO / manifest_path_for(tag)
    if not caminho.exists():
        print(f"✗ a tag {tag} aponta para um commit sem {manifest_path_for(tag)} na árvore — "
              f"manifesto fora da árvore é ausência de release.", file=sys.stderr)
        return 1

    dados = caminho.read_bytes()
    manifest = json.loads(dados.decode("utf-8"))
    lock = {"mold_release": lock_block(
        repository=manifest["release"]["repository"], tag=tag,
        commit_sha=manifest["release"]["commit_sha"], manifest_bytes=dados)}

    violacoes = verify_chain(lock=lock, manifest=manifest, manifest_bytes=dados,
                             tag_commit_sha=commit, parent_sha=parent, changed_paths=mudados)
    if violacoes:
        for v in violacoes:
            print(f"✗ {v}", file=sys.stderr)
        return 1
    print(f"✓ cadeia íntegra: {tag} → {commit[:12]} → {manifest_path_for(tag)} "
          f"→ {manifest_sha(dados)[:12]}")
    return 0


def _cmd_preflight(args) -> int:
    """As pré-condições, com o git de fora. Rede indisponível ⇒ indeterminação, nunca liberação.

    A ordem importa: `git ls-remote` consulta o REMOTO, e a resposta é o estado no instante da
    pergunta. Não é garantia contra uma corrida — a garantia é o `git push` sem `--force`, que é
    atômico no servidor. Este comando existe para que a recusa chegue em segundos em vez de depois
    da validação inteira, e para negar os dois casos que o push sozinho não vê: HEAD movido e
    manifesto já na árvore.
    """
    try:
        head = _git("rev-parse", "HEAD")
        saida = _git("ls-remote", "--tags", "origin")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"• preflight de {args.tag}: não foi possível consultar o git/remoto ({exc}). "
              f"Indeterminação, nunca liberação.", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    tags = [linha.split("refs/tags/", 1)[1].removesuffix("^{}")
            for linha in saida.splitlines() if "refs/tags/" in linha]

    violacoes = preflight_publicacao(
        tag=args.tag, tags_remotas=tags, head_sha=head,
        validado_sha=args.validado or head,
        manifesto_na_arvore=hl.rel_exists(manifest_path_for(args.tag)),
    )
    if violacoes:
        for v in violacoes:
            print(f"✗ {v}", file=sys.stderr)
        return 1
    print(f"✓ preflight de {args.tag}: remoto sem a tag, HEAD em {head[:12]} (o mesmo que foi "
          f"validado), manifesto ausente da árvore.")
    return 0


def _cmd_update_lock(args) -> int:
    caminho = Path(args.manifest)
    if not caminho.is_absolute():
        caminho = hl.REPO / caminho
    if not caminho.exists():
        print(f"✗ manifesto inexistente: {args.manifest}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    dados = caminho.read_bytes()
    manifest = json.loads(dados.decode("utf-8"))
    rel = manifest["release"]
    bloco = lock_block(repository=args.repository or rel["repository"], tag=rel["tag"],
                       commit_sha=rel["commit_sha"], manifest_bytes=dados)
    update_lock(hl.REPO / LOCK, bloco)
    print(f"✓ target.lock ancorado em {bloco['tag']} ({bloco['commit_sha'][:12]}); "
          f"nenhum outro campo tocado.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Raiz de confiança do molde.")
    p.add_argument("--emit", action="store_true")
    p.add_argument("--verify-tag", dest="verify_tag", metavar="TAG")
    p.add_argument("--preflight", metavar="TAG",
                   help="pré-condições da publicação: tag inédita, HEAD imóvel, manifesto ausente")
    p.add_argument("--validado", metavar="SHA",
                   help="o commit em que a validação total rodou (default: HEAD)")
    p.add_argument("--update-lock", action="store_true")
    p.add_argument("--repository")
    p.add_argument("--tag")
    p.add_argument("--commit")
    p.add_argument("--run-id", dest="run_id", default="local")
    p.add_argument("--artifact-digest", dest="artifact_digest",
                   default="sha256:" + "0" * 64)
    p.add_argument("--released-at", dest="released_at")
    p.add_argument("--manifest")
    args = p.parse_args(argv)

    if args.verify_tag:
        args.tag = args.verify_tag
        return _cmd_verify_tag(args)
    if args.preflight:
        args.tag = args.preflight
        return _cmd_preflight(args)
    if args.emit:
        if not (args.repository and args.tag and args.commit):
            p.error("--emit exige --repository, --tag e --commit")
        return _cmd_emit(args)
    if args.update_lock:
        if not args.manifest:
            p.error("--update-lock exige --manifest")
        return _cmd_update_lock(args)
    p.error("escolha um modo: --emit, --verify-tag, --preflight ou --update-lock")
    return 2  # pragma: no cover - parser.error não retorna


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
