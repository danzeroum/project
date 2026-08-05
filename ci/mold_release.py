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
      --run-id N [--run-url U] [--artifact-digest sha256:...]   # escreve o manifesto
  python ci/mold_release.py --verify-tag vX.Y.Z                 # cadeia completa, via git local
  python ci/mold_release.py --update-lock --manifest CAMINHO --repository O/R
Saída: 0 conforme · 1 cadeia quebrada · 2 não foi possível verificar (indeterminação).
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def build_manifest(*, repository: str, tag: str, commit_sha: str, run_id: str,
                   run_url: str | None = None, artifact_digest: str,
                   released_at: str | None = None) -> dict:
    release = {
        "repository": repository,
        "tag": tag,
        "commit_sha": commit_sha,
        "released_at": released_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validation": {"command": VALIDATION_COMMAND, "result": "pass", "run_id": str(run_id)},
        "artifact_digest": artifact_digest,
    }
    if run_url:
        release["validation"]["run_url"] = run_url
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
            f"manifest_sha não confere: o lock espera {str(mr.get('manifest_sha'))[:12]} e os bytes "
            f"do manifesto em {mr.get('manifest_path')} produzem {encontrado[:12]} — ou a tag foi "
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
        run_id=args.run_id, run_url=args.run_url, artifact_digest=args.artifact_digest,
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
    p.add_argument("--update-lock", action="store_true")
    p.add_argument("--repository")
    p.add_argument("--tag")
    p.add_argument("--commit")
    p.add_argument("--run-id", dest="run_id", default="local")
    p.add_argument("--run-url", dest="run_url")
    p.add_argument("--artifact-digest", dest="artifact_digest",
                   default="sha256:" + "0" * 64)
    p.add_argument("--released-at", dest="released_at")
    p.add_argument("--manifest")
    args = p.parse_args(argv)

    if args.verify_tag:
        args.tag = args.verify_tag
        return _cmd_verify_tag(args)
    if args.emit:
        if not (args.repository and args.tag and args.commit):
            p.error("--emit exige --repository, --tag e --commit")
        return _cmd_emit(args)
    if args.update_lock:
        if not args.manifest:
            p.error("--update-lock exige --manifest")
        return _cmd_update_lock(args)
    p.error("escolha um modo: --emit, --verify-tag ou --update-lock")
    return 2  # pragma: no cover - parser.error não retorna


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
