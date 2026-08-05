"""Mordidas da ancoragem do molde (CP-021 / ADR-015).

Cada elo da cadeia é testado ISOLADAMENTE, e essa é a decisão do módulo. Um teste único que
montasse uma cadeia íntegra e a declarasse boa provaria apenas que o caminho feliz funciona — e o
modo de falha que importa aqui não é a cadeia quebrada que ninguém consegue montar, é a cadeia
QUASE íntegra: o hash certo com o commit errado, a tag certa com o manifesto de outra. Por isso
cada teste rompe um elo e exige que a violação nomeada apareça.

`verify_chain` ser função pura é o que torna isto possível sem mock de rede nem repositório de
mentira: os elos chegam como argumento, e romper um é mudar um dicionário.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "ci"))

import harness_lib as hl  # noqa: E402
import mold_release as mr  # noqa: E402

SHA_VALIDADO = "a" * 40
SHA_RELEASE = "b" * 40
SHA_OUTRO = "c" * 40
REPOSITORIO = "danzeroum/project"
TAG = "v1.0.0"


def _manifesto(**over) -> dict:
    doc = mr.build_manifest(
        repository=REPOSITORIO, tag=TAG, commit_sha=SHA_VALIDADO, run_id="42",
        artifact_digest="sha256:" + "d" * 64, released_at="2026-08-05T12:00:00+00:00",
    )
    doc["release"].update(over)
    return doc


def _cadeia(manifesto: dict | None = None, **over):
    """Uma cadeia ÍNTEGRA, pronta para ter exatamente um elo rompido pelo teste."""
    manifesto = manifesto or _manifesto()
    dados = mr.canonical_bytes(manifesto)
    lock = {"mold_release": mr.lock_block(
        repository=REPOSITORIO, tag=TAG, commit_sha=manifesto["release"]["commit_sha"],
        manifest_bytes=dados)}
    kwargs = dict(lock=lock, manifest=manifesto, manifest_bytes=dados,
                  tag_commit_sha=SHA_RELEASE, parent_sha=manifesto["release"]["commit_sha"],
                  changed_paths=[mr.manifest_path_for(TAG)])
    kwargs.update(over)
    return kwargs


# --------------------------------------------------------------------------------------
# O par positivo: a cadeia íntegra passa. Sem ele, um verify_chain que reprovasse TUDO
# passaria em todos os testes negativos abaixo — o verde falso pela porta dos fundos.
# --------------------------------------------------------------------------------------

def test_cadeia_integra_passa():
    assert mr.verify_chain(**_cadeia()) == []


def test_derivado_sem_mold_release_e_recusado():
    """A trava é de schema, nos dois sentidos — é o que impede 'derivado quase ancorado'."""
    lock = {
        "schema_version": "1.0", "metadata_version": "1.0", "source_of_truth": True,
        "generated_from": None, "kind": "derived", "target_sha": "e" * 40,
    }
    problemas = hl.schema_errors("target.lock", "target-lock.schema.json", lock)
    assert any("mold_release" in p for p in problemas), problemas

    # E o verificador de cadeia recusa pelo mesmo motivo, sem depender do schema.
    assert mr.verify_chain(**_cadeia(lock={})) != []


def test_molde_com_mold_release_e_recusado():
    """O simétrico: um molde que declarasse ter nascido de si mesmo."""
    lock = {
        "schema_version": "1.0", "metadata_version": "1.0", "source_of_truth": True,
        "generated_from": None, "kind": "mold", "target_sha": None,
        "mold_release": mr.lock_block(repository=REPOSITORIO, tag=TAG,
                                      commit_sha=SHA_VALIDADO, manifest_bytes=b"{}"),
    }
    assert hl.schema_errors("target.lock", "target-lock.schema.json", lock)


def test_mold_version_com_sha_divergente_e_recusado():
    """Elo 4: lock e manifesto precisam falar da MESMA árvore."""
    kwargs = _cadeia()
    kwargs["lock"]["mold_release"]["commit_sha"] = SHA_OUTRO
    violacoes = mr.verify_chain(**kwargs)
    assert any("commit_sha divergente" in v for v in violacoes), violacoes


def test_lock_com_manifesto_de_outro_commit_reprova():
    """Elo 3: é o elo que detecta tag movida — outro destino, outros bytes, outro hash."""
    kwargs = _cadeia()
    kwargs["lock"]["mold_release"]["manifest_sha"] = "f" * 64
    violacoes = mr.verify_chain(**kwargs)
    assert any("manifest_sha não confere" in v for v in violacoes), violacoes


def test_a_mensagem_MOSTRA_o_digito_que_mudou(monkeypatch):
    """Achado do primeiro derivado a consumir a v1.0.0 (CP-038).

    O corte fixo em 12 caracteres produzia, quando a alteração estava além da posição 12:

        o lock espera 8d5986b6ad3c e os bytes (...) produzem 8d5986b6ad3c

    Dois prefixos IDÊNTICOS sob a palavra "não confere". Quem lê perde tempo achando que o fiscal
    está errado — e o caso não é raro: é o de quem adultera com cuidado, e é o que o teste de borda
    desta casa exercita. A mensagem é o produto do fiscal; uma que se contradiz não fiscaliza.
    """
    kwargs = _cadeia()
    verdadeiro = kwargs["lock"]["mold_release"]["manifest_sha"]
    # Um dígito trocado DEPOIS da posição 12 — o caso que o corte fixo escondia.
    adulterado = verdadeiro[:20] + ("0" if verdadeiro[20] != "0" else "1") + verdadeiro[21:]
    kwargs["lock"]["mold_release"]["manifest_sha"] = adulterado

    msg = next(v for v in mr.verify_chain(**kwargs) if "manifest_sha não confere" in v)
    esperado = mr._hash_curto(adulterado, verdadeiro)
    encontrado = mr._hash_curto(verdadeiro, adulterado)
    assert esperado != encontrado, "os dois lados da mensagem não podem sair iguais"
    assert esperado in msg and encontrado in msg, msg


def test_hashes_iguais_nao_quebram_o_encurtador():
    """Chamado com dois hashes idênticos (não acontece na cadeia, mas a função é pública), o corte
    volta ao mínimo em vez de estourar no `next`."""
    h = "a" * 64
    assert mr._hash_curto(h, h) == "a" * 12


def test_manifesto_que_descreve_outro_pai_reprova():
    """Elo 1/2: o manifesto tem que descrever a árvore que está sendo publicada."""
    violacoes = mr.verify_chain(**_cadeia(parent_sha=SHA_OUTRO))
    assert any("descreve uma árvore que não é a que está sendo publicada" in v
               for v in violacoes), violacoes


def test_commit_de_release_com_carona_reprova():
    """Elo 5, o que fecha o buraco da autorreferência.

    Sem ele, o commit de release poderia carregar código NÃO validado sob a bandeira da validação
    que rodou no pai — e a release inteira afirmaria uma garantia que nunca cobriu esse código.
    """
    violacoes = mr.verify_chain(
        **_cadeia(changed_paths=[mr.manifest_path_for(TAG), "ci/audit_governance.py"]))
    assert any("além do manifesto" in v for v in violacoes), violacoes


def test_indeterminacao_nao_e_violacao():
    """Princípio (h): sem o pai resolvido, o elo não opina — não inventa violação nem aprova.

    Se este teste falhar por 'violação a mais', alguém colapsou indeterminação em fraude, e o
    custo é ensinar que governança vermelha 'provavelmente foi a rede'.
    """
    assert mr.verify_chain(**_cadeia(parent_sha=None, changed_paths=None)) == []


def test_manifesto_com_nome_fora_da_tag_reprova(repo_copy: Path, run_metadata):
    """O nome do arquivo deriva da tag. Livre, duas releases dividiriam caminho e a segunda venceria."""
    manifesto = _manifesto()
    (repo_copy / "harness/releases").mkdir(parents=True, exist_ok=True)
    (repo_copy / "harness/releases/v9.9.9.manifest.json").write_bytes(mr.canonical_bytes(manifesto))
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("nome de arquivo que não deriva da tag" in e for e in erros), erros


def test_manifesto_invalido_reprova(repo_copy: Path, run_metadata):
    """Validação 'fail' não é representável: a categoria 'release publicada com CI vermelho' não existe."""
    manifesto = _manifesto()
    manifesto["release"]["validation"]["result"] = "fail"
    (repo_copy / "harness/releases").mkdir(parents=True, exist_ok=True)
    (repo_copy / f"harness/releases/{TAG}.manifest.json").write_bytes(
        json.dumps(manifesto, indent=2).encode("utf-8"))
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("release-manifest" in e or "estrutural" in e for e in erros), erros


def test_lock_com_manifest_path_de_outra_tag_reprova(repo_copy: Path, run_metadata):
    """O pattern do schema garante a FORMA do caminho; esta é a coerência que ele não vê."""
    import yaml

    lock = repo_copy / "target.lock"
    doc = yaml.safe_load(lock.read_text(encoding="utf-8"))
    doc["mold_release"] = {
        "repository": REPOSITORIO, "tag": TAG, "commit_sha": SHA_VALIDADO,
        "manifest_path": "harness/releases/v9.9.9.manifest.json", "manifest_sha": "0" * 64,
    }
    lock.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    code, erros = run_metadata(repo_copy)
    assert code == 1
    assert any("o caminho é derivado da tag" in e for e in erros), erros


def test_atualizar_carcaca_nao_toca_metadados_do_alvo(repo_copy: Path):
    """A promessa do comando é cirúrgica, e aqui ela é MEDIDA, não lida.

    O comando move a âncora do molde e mais nada. Um `/atualizar-carcaca` que aproveitasse a
    passagem para avançar `target_sha` ou reingerir trocaria uma pergunta por duas, e o vermelho
    seguinte ficaria sem causa atribuível.
    """
    antes = {p: p.read_bytes() for p in repo_copy.rglob("*")
             if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}

    manifesto = _manifesto()
    destino = repo_copy / "harness/releases"
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"{TAG}.manifest.json"
    caminho.write_bytes(mr.canonical_bytes(manifesto))

    proc = subprocess.run(
        [sys.executable, str(repo_copy / "ci/mold_release.py"), "--update-lock",
         "--manifest", mr.manifest_path_for(TAG), "--repository", REPOSITORIO],
        cwd=repo_copy, capture_output=True, text=True,
        env={"HARNESS_REPO_ROOT": str(repo_copy), "PATH": "/usr/bin:/bin",
             "PYTHONPATH": str(repo_copy / "ci")},
    )
    assert proc.returncode == 0, proc.stderr

    depois = {p: p.read_bytes() for p in repo_copy.rglob("*")
              if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}
    mudados = {repo_copy_rel(repo_copy, p) for p in set(antes) | set(depois)
               if antes.get(p) != depois.get(p)}
    assert mudados == {"target.lock", f"harness/releases/{TAG}.manifest.json"}, mudados

    import yaml
    novo = yaml.safe_load((repo_copy / "target.lock").read_text(encoding="utf-8"))
    velho = yaml.safe_load((REPO / "target.lock").read_text(encoding="utf-8"))
    assert novo["mold_release"]["tag"] == TAG
    for chave in ("kind", "target_sha", "schema_version", "source_of_truth", "generated_from"):
        assert novo.get(chave) == velho.get(chave), chave


def repo_copy_rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def test_tag_so_nasce_de_commit_validado(repo_copy: Path, run_auditor):
    """A trava é o passo de validação no workflow de release — e aqui se prova que ele MORDE.

    Remover o passo é o gesto exato de quem quer publicar sem validar. A asserção ADR-015-A5
    existe para que esse gesto fique vermelho; este teste existe para provar que a asserção não é
    decorativa.
    """
    wf = repo_copy / ".github/workflows/release.yml"
    wf.write_text(wf.read_text(encoding="utf-8").replace(
        "run: python ci/validate_all.py", "run: echo pulando a validacao"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f.get("assertion") == "ADR-015-A5" for f in findings), [f["id"] for f in findings]


def test_workflow_de_release_sem_verificacao_de_cadeia_reprova(repo_copy: Path, run_auditor):
    wf = repo_copy / ".github/workflows/release.yml"
    wf.write_text(wf.read_text(encoding="utf-8").replace(
        "ci/mold_release.py --verify-tag", "true #"), encoding="utf-8")
    code, findings = run_auditor("audit_governance", repo_copy)
    assert code == 1
    assert any(f.get("assertion") == "ADR-015-A6" for f in findings), [f["id"] for f in findings]


@pytest.mark.parametrize("ponteiro,chave", [
    ("/allOf/1/then/required", "mold_release"),
    ("/properties/mold_release/required", "manifest_sha"),
])
def test_travas_do_schema_continuam_no_lugar(ponteiro: str, chave: str):
    """Auto-referência: se alguém remover a trava, a asserção que a vigia fica sem alvo."""
    doc = json.loads((REPO / "harness/schemas/target-lock.schema.json").read_text(encoding="utf-8"))
    assert chave in hl.json_pointer(doc, ponteiro)


def test_manifesto_canonico_e_reprodutivel():
    """O hash só significa algo se os bytes forem reprodutíveis. Dois builds iguais, bytes iguais."""
    a = mr.canonical_bytes(_manifesto())
    b = mr.canonical_bytes(_manifesto())
    assert a == b and mr.manifest_sha(a) == mr.manifest_sha(b)
