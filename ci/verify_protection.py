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

DOIS EIXOS, um fiscal: `--branch` pergunta se a `main` é protegida; `--tags` pergunta se a ÂNCORA
das releases é imóvel. São a mesma pergunta sobre dois namespaces de ref, e dependem da mesma raiz
administrativa — separá-las em dois arquivos duplicaria a lógica de indeterminação e criaria duas
cópias que um dia divergiriam.

Uso:  python ci/verify_protection.py [--repo owner/name] [--branch main] [--quiet]
      python ci/verify_protection.py --tags [--tag-glob 'v*']
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


REGRAS_DE_TAG_EXIGIDAS = ("deletion", "non_fast_forward", "update")


def verify_tag_protection(*, rulesets: list[dict] | None, tag_glob: str = "v*") -> list[str]:
    """A imutabilidade da ÂNCORA — segundo eixo da mesma trava externa, não um fiscal novo.

    Por que aqui e não num arquivo próprio: proteção de branch e proteção de tag são a mesma
    pergunta feita sobre dois namespaces de ref, e as duas dependem da mesma raiz administrativa.
    Um fiscal novo duplicaria a lógica de indeterminação e o dia em que uma das cópias divergisse
    ninguém saberia qual acreditar.

    O ADR-025 deixa o workflow CRIAR a ref e conta com o servidor para não deixá-lo MOVÊ-LA. O
    `git push` sem `--force` recusa, mas essa recusa é do cliente: quem tem token e vontade empurra
    com `--force`. O que torna a recusa uma trava é o ruleset — e por isso as três regras exigidas
    são exatamente as que impedem mover e apagar, nunca criar:

      `deletion`         — a tag não some;
      `non_fast_forward` — a tag não é reescrita por force push;
      `update`           — a tag não é reapontada.

    `creation` NÃO é exigida de propósito: exigi-la trancaria o único caminho legítimo de
    publicação, e uma trava que impede o trabalho legítimo é desligada por quem tem trabalho a
    fazer.

    `rulesets=None` é indeterminação (a API responde 403/404 tanto para "não há" quanto para "você
    não pode ver"), e quem a trata é o chamador — igual ao eixo de branch, pela mesma razão.
    """
    if rulesets is None:
        return []

    cobrem = []
    for rs in rulesets:
        if rs.get("target") != "tag" or rs.get("enforcement") != "active":
            continue
        inclui = ((rs.get("conditions") or {}).get("ref_name") or {}).get("include") or []
        if any(i == "~ALL" or i == f"refs/tags/{tag_glob}" or i == "refs/tags/**" for i in inclui):
            cobrem.append(rs)

    if not cobrem:
        return [f"nenhum ruleset de tag ATIVO cobre refs/tags/{tag_glob} — a âncora das releases "
                f"depende de a tag não se mover, e nada impede que ela se mova. O `git push` sem "
                f"--force do workflow é recusa do cliente; a trava é do servidor"]

    v: list[str] = []
    for rs in cobrem:
        nome = rs.get("name") or rs.get("id")
        tipos = {r.get("type") for r in (rs.get("rules") or [])}
        faltando = [t for t in REGRAS_DE_TAG_EXIGIDAS if t not in tipos]
        if faltando:
            v.append(f"o ruleset de tag {nome!r} não exige {', '.join(faltando)} — sem essas "
                     f"regras a tag pode ser reapontada ou apagada, e todo derivado que a cita "
                     f"passa a afirmar procedência sobre conteúdo que já não está lá")
        if rs.get("bypass_actors"):
            v.append(f"o ruleset de tag {nome!r} tem bypass list NÃO-VAZIA — quem pode bypassar "
                     f"pode mover a tag, e a trava passa a valer só para quem não precisaria dela")
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


def _rulesets_de_tag(repo: str, token: str) -> list[dict] | None:
    """Os rulesets de tag COM suas regras. None = não foi possível olhar.

    Duas chamadas porque a listagem devolve resumo sem `rules`, e decidir sobre um ruleset sem ver
    suas regras seria concluir a partir do nome dele.
    """
    lista = _api(f"https://api.github.com/repos/{repo}/rulesets?includes_parents=true", token)
    if lista is None:
        return None
    detalhes = []
    for rs in lista:
        if rs.get("target") != "tag":
            continue
        completo = _api(f"https://api.github.com/repos/{repo}/rulesets/{rs['id']}", token)
        if completo is None:
            return None
        detalhes.append(completo)
    return detalhes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Camada local da trava externa.")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--tags", action="store_true",
                        help="eixo de TAGS: a âncora das releases é imóvel?")
    parser.add_argument("--tag-glob", dest="tag_glob", default="v*")
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

    externo = estado_da_auditoria_externa(harness_doc)

    if args.tags:
        try:
            rulesets = _rulesets_de_tag(args.repo, token)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"• protection_unverifiable: não foi possível listar os rulesets ({exc}).",
                  file=sys.stderr)
            return EXIT_UNVERIFIABLE
        if rulesets is None:
            print(f"• protection_unverifiable: a API não distingue 'sem ruleset de tag' de 'sem "
                  f"permissão para ver' em {args.repo}. Estado indeterminado.", file=sys.stderr)
            return EXIT_UNVERIFIABLE

        violacoes = verify_tag_protection(rulesets=rulesets, tag_glob=args.tag_glob)
        if not violacoes:
            if not args.quiet:
                print(f"✓ proteção: refs/tags/{args.tag_glob} imóvel — o ruleset recusa mover e "
                      f"apagar, e deixa criar (que é o caminho legítimo do release.yml).")
            return 0

        # Enquanto external_audit está DESLIGADA, este eixo REPORTA e não bloqueia — a mesma
        # doutrina do eixo de branch, pela mesma razão: repositório vermelho por condição que
        # ninguém aqui satisfaz é repositório cujo fiscal se aprende a ignorar. O risco tem data.
        cabeca = "✗ proteção de tag" if externo.get("enabled") else "• proteção de tag (informativo)"
        print(f"{cabeca}: {len(violacoes)} lacuna(s):", file=sys.stderr)
        for m in violacoes:
            print(f"  - {m}", file=sys.stderr)
        if externo.get("enabled"):
            return 1
        print(f"  Autoridade externa DESLIGADA: lacuna é risco aceito COM DATA em "
              f"{externo.get('accepted_risk', 'RISK-EXT-001')}. Ligar external_audit torna estas "
              f"linhas bloqueantes sem mudar uma linha de código.", file=sys.stderr)
        return 0

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
