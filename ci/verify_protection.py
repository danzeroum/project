#!/usr/bin/env python3
"""Camada local da trava externa — a proteção declarada está de fato ligada?

`harness.yaml` declara que o fiscal real de `protected_paths` é CODEOWNERS mais branch protection.
Até aqui isso era uma frase: nenhum fiscal conferia que a proteção estava ligada. Este arquivo
confere.

E ELE NÃO BASTA, o que precisa ficar escrito aqui e não só na CP: este passo mora no MESMO
repositório que fiscaliza. Um PR com privilégio suficiente remove o passo e a asserção que o vigia
no mesmo commit, e o CI fica verde porque a trava saiu junto com quem reclamaria dela. É circular
por construção, e nenhuma quantidade de código local resolve — só um ruleset administrado fora
daqui. Enquanto ele não existir, `harness.yaml:external_audit.enabled` fica `false` e o estado
aparece a cada execução, citando o risco datado. Lacuna barulhenta em vez de silenciosa.

Núcleo puro, camada de rede separada — mesma divisão do ci/mold_release.py e do
ci/verify_approval.py, pela mesma razão: "a proteção está desligada" e "não consegui perguntar"
exigem reações opostas (princípio (h)).

Uso:  python ci/verify_protection.py [--repo owner/name] [--branch main] [--quiet]
Saída: 0 protegido · 1 proteção ausente ou caminho sem dono · 3 protection_unverifiable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import harness_lib as hl
from harness_lib import HarnessError

HARNESS_YAML = "harness/harness.yaml"
CODEOWNERS = ".github/CODEOWNERS"

EXIT_UNVERIFIABLE = 3


# --------------------------------------------------------------------------------------
# Núcleo puro
# --------------------------------------------------------------------------------------

def verify_protection(*, protection: dict | None, codeowners: list[str],
                      protected_paths: list[str], branch: str = "main") -> list[str]:
    """Violações da proteção declarada. Lista vazia = a declaração corresponde ao real.

    `protection=None` NÃO entra aqui como violação: ausência de resposta da API é indeterminação e
    quem a trata é o chamador. Inventar violação a partir de silêncio é o modo de falha que
    transforma um token sem escopo em alarme de fraude.
    """
    v: list[str] = []
    if protection is None:
        return v

    if not protection:
        return [f"a branch '{branch}' não tem proteção alguma configurada — "
                f"harness.yaml declara CODEOWNERS + branch protection como o fiscal REAL dos "
                f"protected_paths, e ele está desligado"]

    reviews = protection.get("required_pull_request_reviews")
    if not reviews:
        v.append(f"'{branch}' não exige pull request review — sem isso, um push direto "
                 f"atravessa toda a governança declarada")
    elif not reviews.get("require_code_owner_reviews"):
        v.append(f"'{branch}' exige review, mas não review de CODE OWNER — é o elo que faz "
                 f"protected_paths significar alguma coisa; sem ele, qualquer aprovador serve "
                 f"para mudar um fiscal")

    if protection.get("allow_force_pushes", {}).get("enabled"):
        v.append(f"'{branch}' permite force push — histórico reescrevível torna qualquer âncora "
                 f"por commit (target.lock, mold_release, executed_in) uma afirmação sobre "
                 f"conteúdo que pode ter mudado")

    donos = [linha.split()[0].lstrip("/").rstrip("/")
             for linha in codeowners
             if linha.strip() and not linha.strip().startswith("#")]
    for p in protected_paths:
        stem = p.rstrip("/")
        if not any(stem == d or stem.startswith(d + "/") or d.startswith(stem) for d in donos):
            v.append(f"protected_path '{p}' não é coberto por nenhuma regra de CODEOWNERS — "
                     f"a proteção é declarada, e ninguém precisa revisar a mudança")
    return v


def estado_da_auditoria_externa(harness_doc: dict) -> dict:
    """O bloco declarado. Ausente ⇒ tratado como desligado, nunca como ligado por omissão."""
    return (harness_doc or {}).get("external_audit") or {"enabled": False}


# --------------------------------------------------------------------------------------
# Camada com rede
# --------------------------------------------------------------------------------------

def _api(url: str, token: str) -> object | None:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "harness-verify-protection",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - URL montada aqui
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            # 404 aqui significa "sem proteção" OU "sem permissão para ver", e a API não
            # distingue os dois. Indeterminação, portanto — nunca a conclusão mais grave.
            return None
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Camada local da trava externa.")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        harness_doc = hl.read_yaml(HARNESS_YAML) or {}
    except HarnessError as exc:
        print(f"✗ proteção: {exc}", file=sys.stderr)
        return 2

    protegidos = (harness_doc.get("repository") or {}).get("protected_paths") or []
    codeowners = hl.read_text(CODEOWNERS).splitlines() if hl.rel_exists(CODEOWNERS) else []

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token or not args.repo:
        print("• protection_unverifiable: sem credencial ou repositório para consultar a "
              "proteção da branch.\n  Indeterminação auditável — nunca 'protegido' por ausência "
              "de prova.", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    try:
        protection = _api(
            f"https://api.github.com/repos/{args.repo}/branches/{args.branch}/protection", token)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"• protection_unverifiable: não foi possível consultar a proteção ({exc}).",
              file=sys.stderr)
        return EXIT_UNVERIFIABLE

    if protection is None:
        print(f"• protection_unverifiable: a API não distingue 'sem proteção' de 'sem permissão "
              f"para ver' em {args.repo}@{args.branch}. Estado indeterminado.", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    violacoes = verify_protection(protection=protection, codeowners=codeowners,
                                  protected_paths=protegidos, branch=args.branch)
    externo = estado_da_auditoria_externa(harness_doc)
    if violacoes:
        print(f"✗ proteção: {len(violacoes)} violação(ões):", file=sys.stderr)
        for m in violacoes:
            print(f"  - {m}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"✓ proteção: '{args.branch}' protegida e {len(protegidos)} protected_path(s) com dono.")
        if not externo.get("enabled"):
            print("• autoridade externa DESLIGADA: esta verificação mora no mesmo repositório que "
                  "fiscaliza, e um PR privilegiado remove o passo e a asserção juntos. "
                  f"Risco aceito com data em {externo.get('accepted_risk', 'RISK-EXT-001')}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
