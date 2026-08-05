"""Mordidas do portão do auto-merge (CP-037 / ADR-029).

Duas perguntas diferentes, e este arquivo as mantém separadas de propósito:

  VERIFICAÇÃO — cada uma das três condições barra o seu desvio? É o bloco de cima, e ele fala com
  o núcleo puro. Sem rede, sem disco, sem relógio: os três cenários que importam
  (só-atestado/App, atestado+extra/App, só-atestado/humano) são três chamadas de função.

  VALIDAÇÃO — o caminho diário inteiro (cron → atestado → PR → merge → consumo) roda sem toque
  humano, inclusive no pior horário? É o bloco de baixo, e ele fala com o CALENDÁRIO e com o
  workflow. Nenhum teste do bloco de cima responderia isso: um portão perfeito num ciclo que não
  fecha é um portão que ninguém atravessa.

A distinção não é acadêmica. O erro que ela previne é o de sempre nesta casa — correto contra os
próprios fixtures, errado contra o mundo.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import automerge_gate as ag  # noqa: E402

ATESTADO = "harness/state/protection-attestation.json"
APP = "harness-authority[bot]"
WORKFLOW = REPO / ".github/workflows/atestado-automerge.yml"


def _decidir(**kw):
    base = dict(arquivos=[ATESTADO], autor_login=APP, autor_tipo="Bot",
                emissor_autorizado="harness-authority", caminho_atestado=ATESTADO)
    return ag.decidir(**{**base, **kw})


# --------------------------------------------------------------------------------------
# VERIFICAÇÃO — cada condição barra o seu desvio
# --------------------------------------------------------------------------------------

def test_o_PR_diario_REAL_libera():
    """Cenário 1: só o atestado, aberto pelo App. É o caso que precisa passar todo dia."""
    d = _decidir()
    assert d.liberar is True
    assert d.codigos == ("AUTORIZADO",)


def test_atestado_MAIS_um_arquivo_nao_libera_e_diz_qual():
    """Cenário 2: o App abre um PR com o atestado e um segundo arquivo.

    Um PR que muda o atestado E outra coisa é um PR que muda outra coisa com o atestado de carona.
    O motivo tem que NOMEAR o arquivo extra — 'diff fora do escopo' manda ler o diff de novo.
    """
    d = _decidir(arquivos=[ATESTADO, "ci/audit_governance.py"])
    assert d.liberar is False
    assert "DIFF-ALEM-DO-ATESTADO" in d.codigos
    assert "ci/audit_governance.py" in " ".join(d.motivos)


def test_humano_tocando_o_atestado_nao_libera():
    """Cenário 3: o arquivo certo, a identidade errada.

    É o cenário que dá sentido a todo o resto: se qualquer PR com o arquivo certo auto-mergeasse,
    o humano com direito de merge recuperaria exatamente o poder que o atestado existe para tirar
    dele — escrever o carimbo e integrá-lo sem ninguém olhar.
    """
    d = _decidir(autor_login="danzeroum", autor_tipo="User")
    assert d.liberar is False
    assert "AUTOR-NAO-E-A-AUTORIDADE" in d.codigos


def test_conta_humana_com_o_NOME_do_app_nao_basta():
    """O login é digitável; o tipo é atribuído pelo GitHub. Exigir os dois não é redundância."""
    d = _decidir(autor_login=APP, autor_tipo="User")
    assert d.liberar is False
    assert "AUTOR-NAO-E-A-AUTORIDADE" in d.codigos


def test_os_dois_desvios_juntos_produzem_os_DOIS_motivos():
    """Princípio (h): retornar no primeiro faria a segunda rodada descobrir algo que já estava lá."""
    d = _decidir(arquivos=[ATESTADO, "README.md"], autor_login="danzeroum", autor_tipo="User")
    assert d.liberar is False
    assert set(d.codigos) == {"AUTOR-NAO-E-A-AUTORIDADE", "DIFF-ALEM-DO-ATESTADO"}


def test_diff_vazio_nao_libera():
    """'Não consegui ver o diff' tem a mesma aparência de 'o diff está conforme', e as duas pedem
    reações opostas."""
    d = _decidir(arquivos=[])
    assert d.liberar is False
    assert "PORTAO-SEM-DIFF" in d.codigos


@pytest.mark.parametrize("faltando", ["emissor_autorizado", "caminho_atestado"])
def test_sem_declaracao_o_portao_NAO_libera(faltando):
    """Sem a declaração, as comparações seriam feitas contra string vazia — e liberariam por
    vacuidade. Um portão que não sabe contra o que comparar tem uma resposta segura só."""
    d = _decidir(**{faltando: ""})
    assert d.liberar is False
    assert d.codigos == ("PORTAO-SEM-DECLARACAO",)


def test_o_caminho_do_atestado_vem_do_harness_e_nao_do_teste():
    """A igualdade é contra o que `harness.yaml` declara. Se alguém mudar o `attestation_path` e
    esquecer o portão, é aqui que aparece — e não em produção, às 06:17Z."""
    doc = yaml.safe_load((REPO / "harness/harness.yaml").read_text(encoding="utf-8"))
    externo = doc["external_audit"]
    d = ag.decidir(arquivos=[externo["attestation_path"]],
                   autor_login=f"{externo['authorized_issuer']['identity']}[bot]",
                   autor_tipo="Bot",
                   emissor_autorizado=externo["authorized_issuer"]["identity"],
                   caminho_atestado=externo["attestation_path"])
    assert d.liberar is True


@pytest.mark.parametrize("intruso", [
    "harness/state/outro.json",          # vizinho do atestado
    "harness/harness.yaml",              # a própria declaração
    ".github/workflows/governance.yml",  # o fiscal
    "ci/automerge_gate.py",              # o portão
])
def test_NENHUM_outro_caminho_entra_junto(intruso):
    """A asserção que torna caro alargar isto, dita como teste: a comparação é uma IGUALDADE
    contra UM caminho. Um `startswith` passaria nos dois primeiros casos aqui."""
    assert _decidir(arquivos=[ATESTADO, intruso]).liberar is False
    assert _decidir(arquivos=[intruso]).liberar is False


# --------------------------------------------------------------------------------------
# VALIDAÇÃO — o caminho diário fecha sozinho, inclusive no pior horário
# --------------------------------------------------------------------------------------

def _cron_do_atestado() -> tuple[int, int]:
    """Hora do cron da autoridade, lida do atestado real em vez de restatada aqui.

    O `checked_at` do carimbo na árvore é a hora em que a autoridade de fato passou — melhor fonte
    que uma constante neste arquivo, que envelheceria em silêncio se o cron mudasse.
    """
    import json
    doc = json.loads((REPO / ATESTADO).read_text(encoding="utf-8"))["attestation"]
    t = datetime.fromisoformat(doc["checked_at"])
    return t.hour, t.minute


def test_a_folga_entre_dois_carimbos_e_de_uma_hora_e_isso_e_deliberado():
    """A aritmética que o ADR-029 declara, conferida contra o atestado real.

    25h de validade e 24h de intervalo compram exatamente 1h de margem: o carimbo de hoje vence
    uma hora DEPOIS de o de amanhã nascer. A margem existe para absorver fila de runner e duração
    de checks — não para absorver um humano dormindo, que é precisamente o que esta CP tira do
    caminho.
    """
    import json
    doc = json.loads((REPO / ATESTADO).read_text(encoding="utf-8"))["attestation"]
    nasceu = datetime.fromisoformat(doc["checked_at"])
    vence = datetime.fromisoformat(doc["expires_at"])
    validade = vence - nasceu
    proximo = nasceu + timedelta(days=1)

    assert validade == timedelta(hours=25), validade
    folga = vence - proximo
    assert folga == timedelta(hours=1), folga
    assert proximo < vence, "o próximo carimbo nasce ANTES de este vencer — sem janela cega"


def test_um_cron_perdido_BLOQUEIA_e_o_seguinte_DESTRAVA_sem_humano():
    """A promessa 'sem depender de ninguém perceber', testada no pior horário.

    O bloqueio é a promessa cumprida, não a falha. O que precisa ser verdade é o destravamento:
    a execução seguinte abre um PR cujo conteúdo JÁ É o atestado novo, os checks rodam contra o
    merge (que portanto contém o carimbo válido) e passam, e o portão libera o auto-merge. Nenhum
    humano no caminho — nem para bloquear, nem para destravar.

    O que este teste consegue provar sem GitHub: que o portão libera um PR de atestado
    independentemente de o carimbo ANTERIOR estar vencido. Se a decisão dependesse do estado da
    base, um molde bloqueado nunca se destravaria — e o bloqueio seria permanente em vez de
    temporário, que é a diferença entre uma trava e um tijolo.
    """
    assert not any("expir" in nome or "valid" in nome
                   for nome in ag.decidir.__code__.co_varnames), \
        "o portão não deve olhar validade do atestado: essa é a pergunta do consumo, não do merge"
    assert _decidir().liberar is True


def _carimbar(root: Path, *, expira: datetime) -> None:
    """Escreve, na cópia, o atestado que a autoridade entregaria — derivado do REAL.

    Derivado e não inventado: se o schema do atestado ganhar um campo obrigatório, um JSON montado
    à mão aqui continuaria passando neste teste e falhando em produção.
    """
    import json
    caminho = root / ATESTADO
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    doc["attestation"]["checked_at"] = (expira - timedelta(hours=25)).isoformat(timespec="seconds")
    doc["attestation"]["expires_at"] = expira.isoformat(timespec="seconds")
    caminho.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_o_CICLO_INTEIRO_se_destrava_sozinho_depois_de_um_cron_perdido(repo_copy, run_auditor):
    """VALIDAÇÃO, não verificação: o caminho diário fecha sem ninguém tocar nele.

    Encenado na ordem em que aconteceria às 3h da manhã:

      1. um dia de cron se perde e o carimbo vence  → o molde BLOQUEIA. É a promessa cumprida, não
         a falha: sem isso, proteção desligada seguiria verde indefinidamente.
      2. a execução seguinte abre um PR cujo conteúdo JÁ É o carimbo novo → os checks rodam contra
         o merge, que portanto contém o atestado válido, e passam.
      3. o portão libera o auto-merge desse PR.

    O passo 2 é o que este teste realmente prova, e é o que nenhum teste do núcleo puro alcança:
    que o vermelho do passo 1 é REVERSÍVEL pelo próprio conteúdo do PR. Se `validate_all` seguisse
    vermelho com o carimbo novo aplicado, os checks nunca ficariam verdes, o auto-merge nunca
    dispararia, e o bloqueio seria permanente — a diferença entre uma trava e um tijolo.
    """
    agora = datetime.now(timezone.utc)

    _carimbar(repo_copy, expira=agora - timedelta(hours=2))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1, "carimbo vencido tinha de bloquear"
    assert any(f["id"].endswith("ATESTADO-EXPIRADO") for f in findings), [f["id"] for f in findings]

    _carimbar(repo_copy, expira=agora + timedelta(hours=25))
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 0, [f["id"] for f in findings if f.get("severity") != "info"]

    assert _decidir().liberar is True, "e o PR que trouxe esse carimbo é auto-mergeável"


def test_recusar_NAO_reprova_o_PR():
    """Um PR humano que toca o atestado é legítimo; ele só não é auto-mergeável.

    Deixá-lo vermelho ensinaria a ignorar o vermelho — o mesmo motivo pelo qual o achado de
    'auditoria desligada' é `info` (ADR-019). Só a indeterminação sai diferente de 0, e ela sai
    pela camada de I/O.
    """
    import inspect
    fonte = inspect.getsource(ag.main)
    assert "return 0" in fonte and "return 2" in fonte
    assert re.search(r"return 2", fonte), "a indeterminação precisa de código próprio"


# --------------------------------------------------------------------------------------
# O workflow — o que o núcleo puro não alcança
# --------------------------------------------------------------------------------------

def test_o_workflow_nao_traz_o_head_do_PR_para_o_runner():
    """O modo de falha clássico do `pull_request_target`: um job com `contents: write` que faz
    checkout do head executa código de quem propôs, com o privilégio de quem julga."""
    texto = WORKFLOW.read_text(encoding="utf-8")
    doc = yaml.safe_load(texto)
    assert "pull_request_target" in doc[True], doc[True]
    passos = doc["jobs"]["portao"]["steps"]
    checkouts = [p for p in passos if "checkout" in str(p.get("uses", ""))]
    assert checkouts, "sem checkout o portão não teria o fiscal para rodar"
    for c in checkouts:
        assert "ref" not in (c.get("with") or {}), \
            f"checkout com `ref` explícito em pull_request_target: {c}"


def test_o_passo_que_habilita_vem_DEPOIS_do_que_decide_e_depende_dele():
    """Ordem sem condição é encenação; condição sem ordem não existe. As duas, por índice."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    nomes = [p.get("name", "") for p in doc["jobs"]["portao"]["steps"]]
    i_decide = next(i for i, n in enumerate(nomes) if "Decidir" in n)
    i_habilita = next(i for i, n in enumerate(nomes) if "Habilitar" in n)
    assert i_decide < i_habilita, nomes

    habilita = doc["jobs"]["portao"]["steps"][i_habilita]
    assert "steps.portao.outputs.liberar == 'true'" in habilita["if"], habilita.get("if")


def test_capacidade_ausente_no_ambiente_AVISA_e_nao_reprova():
    """Duas falhas diferentes, duas reações — e esta distinção veio de um achado real.

    Sondado em 05/08/2026: `Allow auto-merge` está DESMARCADO neste repositório. Isso não é
    defeito deste PR nem deste workflow; é uma capacidade que falta no ambiente, e o fallback dela
    é o estado anterior à CP-037 — o PR diário integrado à mão.

    A primeira versão deste passo reprovava o job em qualquer erro. Teria pintado de vermelho TODO
    PR de atestado até alguém marcar uma caixa em Settings, e vermelho permanente é como um fiscal
    se torna ignorado (ADR-019) — o mesmo motivo pelo qual o achado de 'auditoria desligada' é
    `info`.

    Qualquer OUTRO erro continua reprovando: token sem escopo, PR em estado inesperado, API fora.
    Esses significam que o desenho não fez o que promete, e aí o vermelho é a informação certa.
    """
    texto = WORKFLOW.read_text(encoding="utf-8")
    habilita = texto[texto.index("Habilitar o auto-merge NATIVO"):]

    aviso = habilita.index("::warning::")
    erro = habilita.index("::error::")
    assert aviso < erro, "a capacidade ausente avisa; o resto reprova — nessa ordem"
    assert "Allow auto-merge" in habilita, "o aviso precisa carregar a ação de admin exata"
    assert re.search(r"::warning::[\s\S]*?exit 0", habilita), \
        "o caminho da capacidade ausente tem de sair 0 — o fallback é manual, não quebrado"
    assert habilita.rstrip().endswith("exit 1"), \
        "o caminho não classificado tem de reprovar; um `exit 0` no fim engoliria todo erro novo"


def test_o_workflow_usa_o_auto_merge_NATIVO_e_nao_mergeia_por_conta_propria():
    """`--auto` entrega o julgamento dos checks a quem tem a resposta. Uma chamada à API de merge,
    ou um `--admin`, faria este workflow decidir sobre um estado que ainda vai mudar."""
    texto = WORKFLOW.read_text(encoding="utf-8")
    assert "--auto" in texto
    assert "--admin" not in texto
    assert "pulls/" not in texto and "/merge" not in texto
