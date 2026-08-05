#!/usr/bin/env python3
"""Aprovação de change-proposal `high` — provada contra o conteúdo que foi integrado.

`human_approval_required: true` declara que aval era NECESSÁRIO. Jamais que aval HOUVE. A distância
entre as duas frases é o buraco que este fiscal fecha: `approved_by` deixa de ser um login digitado
pelo autor e passa a ser um review resolvido contra a API.

A divisão é a mesma do ci/mold_release.py, porque o problema é o mesmo: `verify_approval` é FUNÇÃO
PURA — recebe a proposta, o PR e os reviews já buscados, e devolve violações. Quem fala com a rede
é o CLI. Sem essa separação, "não há credencial" e "alguém forjou um aval" produziriam o mesmo
vermelho, e a leitura barata venceria por hábito ('deve ser o token'). Princípio (h) do plano:
fraude reprova com código de violação; ausência de credencial é indeterminação auditável.

Uso:  python ci/verify_approval.py [--repo owner/name] [--quiet]
Saída: 0 conforme · 1 aprovação inválida (violação) · 3 approval_unverifiable (indeterminação).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import harness_lib as hl
from harness_lib import HarnessError

PROPOSALS_DIR = "harness/change-proposals"

# Indeterminação tem código PRÓPRIO, e não é 2 por acaso: 2 já significa "o fiscal não conseguiu
# fiscalizar" em todo o resto da harness, e aqui o fiscal conseguiu perfeitamente — o que falta é
# credencial. Dar-lhe um código distinto é o que permite ao CI tratar os dois casos diferente sem
# ler mensagem de texto.
EXIT_UNVERIFIABLE = 3


# --------------------------------------------------------------------------------------
# Núcleo puro
# --------------------------------------------------------------------------------------

def verify_approval(*, proposal: dict, pr: dict, reviews: list[dict]) -> list[str]:
    """Violações da aprovação declarada. Lista vazia = aprovação legítima para este conteúdo.

    Os modos de fraude que cada bloco recusa estão nomeados no comentário — não porque o código
    seja obscuro, mas porque a ausência de um bloco é invisível: quem lê um verificador não vê a
    checagem que ninguém escreveu.
    """
    v: list[str] = []
    aprovacao = proposal.get("approved_by") or {}
    cp_id = proposal.get("id", "?")

    if not aprovacao:
        return [f"{cp_id}: declarada 'executed' com risco alto e sem approved_by — "
                f"'aval necessário' não é 'aval houve'"]

    review = next((r for r in reviews if r.get("id") == aprovacao.get("review_id")), None)

    # Fraude 1 — citar um review que não existe. O caso mais simples, e o que qualquer
    # verificação puramente textual deixaria passar.
    if review is None:
        return [f"{cp_id}: o review {aprovacao.get('review_id')} declarado em approved_by não "
                f"existe no PR #{aprovacao.get('pr_number')} — aprovação citada, nunca prestada"]

    # Fraude 2 — citar um review que existe mas não aprova (COMMENTED, CHANGES_REQUESTED).
    if review.get("state") != "APPROVED":
        v.append(f"{cp_id}: o review {review.get('id')} está '{review.get('state')}', não "
                 f"'APPROVED' — um comentário não é um aval")

    # Fraude 3 — auto-aprovação com um passo extra. Continua sendo auto-aprovação.
    autor_pr = (pr.get("user") or {}).get("login")
    aprovador = (review.get("user") or {}).get("login")
    if aprovador and autor_pr and aprovador == autor_pr:
        v.append(f"{cp_id}: o aprovador '{aprovador}' é o autor do PR — auto-aprovação com um "
                 f"passo a mais continua sendo auto-aprovação")

    if aprovador and aprovador != aprovacao.get("login"):
        v.append(f"{cp_id}: approved_by declara o login '{aprovacao.get('login')}' e o review "
                 f"{review.get('id')} foi submetido por '{aprovador}'")

    # Fraude 4 — a que motiva o endurecimento desta rodada. Dependendo da configuração de
    # dismissal, o estado APPROVED SOBREVIVE a pushes novos: aprova-se o diff A, empurra-se o
    # diff B, e a API continua respondendo APPROVED. "Aprovado" precisa significar "aprovado para
    # este conteúdo", senão o aval humano vira carimbo que se obtém uma vez e se reusa.
    head = pr.get("head", {}).get("sha")
    commit_do_review = review.get("commit_id")
    if head and commit_do_review and commit_do_review != head:
        v.append(f"{cp_id}: o review {review.get('id')} aprovou {str(commit_do_review)[:12]} e o "
                 f"conteúdo integrado é {str(head)[:12]} — aprovação anterior ao último push, "
                 f"ainda que a API a exponha como APPROVED")

    # Fraude 5 — apontar o aval para um PR e a execução para outro.
    executado = proposal.get("executed_in") or {}
    if executado.get("pr_number") != aprovacao.get("pr_number"):
        v.append(f"{cp_id}: executed_in cita o PR #{executado.get('pr_number')} e approved_by "
                 f"cita o PR #{aprovacao.get('pr_number')} — o aval precisa ser DESTE merge")

    merge = pr.get("merge_commit_sha")
    if merge and executado.get("merge_commit_sha") and executado["merge_commit_sha"] != merge:
        v.append(f"{cp_id}: executed_in declara o merge {executado['merge_commit_sha'][:12]} e o "
                 f"PR #{executado.get('pr_number')} foi integrado em {merge[:12]}")

    return v


def propostas_que_exigem_prova() -> list[tuple[str, dict]]:
    """CPs `executed` de risco alto — as únicas cuja aprovação é verificável e exigida.

    Lidas do diretório, nunca de uma lista: uma proposta nova nasce coberta, que é a lição do
    CP-020 atravessando o plano inteiro.
    """
    out: list[tuple[str, dict]] = []
    d = hl.REPO / PROPOSALS_DIR
    if not d.exists():
        return out
    for path in sorted(d.glob("*.yaml")):
        try:
            doc = hl.read_yaml(hl.rel(path)) or {}
        except HarnessError:
            continue
        p = doc.get("proposal") or {}
        if p.get("status") != "executed":
            continue
        if (p.get("risk_assessment") or {}).get("level") not in ("high", "critical"):
            continue
        out.append((hl.rel(path), p))
    return out


# --------------------------------------------------------------------------------------
# Camada com rede
# --------------------------------------------------------------------------------------

def _api(url: str, token: str) -> object:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "harness-verify-approval",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - URL montada aqui
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aprovação provada no conteúdo integrado.")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    alvos = propostas_que_exigem_prova()
    if not alvos:
        if not args.quiet:
            print("✓ aprovação: nenhuma proposta 'executed' de risco alto a verificar.")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token or not args.repo:
        # approval_unverifiable. NÃO é verde e NÃO é fraude: é o estado de quem não tem como olhar.
        print(f"• approval_unverifiable: {len(alvos)} proposta(s) 'executed' de risco alto sem "
              f"credencial ou repositório para resolver o review.\n"
              f"  Indeterminação auditável — nunca aprovação por ausência de prova.", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    violacoes: list[str] = []
    indeterminadas: list[str] = []
    for rel, proposta in alvos:
        pr_num = (proposta.get("executed_in") or {}).get("pr_number")
        try:
            pr = _api(f"https://api.github.com/repos/{args.repo}/pulls/{pr_num}", token)
            reviews = _api(f"https://api.github.com/repos/{args.repo}/pulls/{pr_num}/reviews", token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            indeterminadas.append(f"{rel}: não foi possível consultar o PR #{pr_num} ({exc})")
            continue
        violacoes.extend(f"{rel}: {m}" for m in
                         verify_approval(proposal=proposta, pr=pr, reviews=reviews))

    if violacoes:
        print(f"✗ aprovação: {len(violacoes)} violação(ões):", file=sys.stderr)
        for m in violacoes:
            print(f"  - {m}", file=sys.stderr)
        return 1
    if indeterminadas:
        print("• approval_unverifiable:", file=sys.stderr)
        for m in indeterminadas:
            print(f"  - {m}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    if not args.quiet:
        print(f"✓ aprovação: {len(alvos)} proposta(s) com aval provado no conteúdo integrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
