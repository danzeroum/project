#!/usr/bin/env bash
# Paridade local: instala EXATAMENTE o que o CI instala, e roda EXATAMENTE o que ele roda.
#
# O objetivo não é conveniência — é fechar a distância entre "passa aqui" e "passa lá". Um
# ambiente local resolvido de outro jeito produz um verde que o CI limpo contradiz, e "na minha
# máquina passa" é o oposto do que um repositório de governança pode tolerar.
#
# --require-hashes é o que torna a paridade verificável em vez de afirmada: sem ele, um cache
# envenenado ou um índice trocado entregaria outro artefato com o mesmo nome e versão.
#
# Este script NÃO conserta nada. Ele instala, roda e reporta — a fronteira do R-01: o fiscal
# sugere o comando, quem executa é quem decidiu.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

echo "■ Instalando do lockfile do CI (requirements-ci.txt), com verificação de hash"
if ! pip install --require-hashes --quiet -r requirements-ci.txt; then
  cat >&2 <<'ERRO'

✗ A instalação com hash falhou.

  A causa mais comum não é um defeito: --require-hashes fixa ARTEFATOS, e wheel é específico de
  plataforma. requirements-ci.txt é gerado para o que o CI usa (Linux x86_64, CPython 3.11).

  Falhar aqui é o comportamento CERTO. A alternativa seria cair para outra resolução em silêncio
  — exatamente a divergência que o lockfile existe para impedir.

  O que fazer:
    · na mesma plataforma do CI:  pip install --require-hashes -r requirements-ci.txt
    · em outra plataforma, para trabalhar sem paridade de artefato (e ciente disso):
        pip install -e ".[dev]"
    · para regenerar o lock na sua plataforma, veja harness/policies/paridade-local.md

ERRO
  exit 1
fi

echo
echo "■ Validação total (o mesmo comando do governance.yml)"
python ci/validate_all.py

echo
echo "■ Testes dos fiscais (o mesmo comando do governance.yml)"
pytest tests/governance -q

echo
echo "✓ Paridade local: o que passou aqui é o que o CI roda."
