# Política: paridade local, e por que duração nunca é gate

## Duração de CI nunca é gate de merge

O gate de cache de "≥30% de ganho em 5 runs" está **revogado** (R-12). Um threshold de duração
mistura cold start, warm start, fila do GitHub, rede e tamanho de runner num único número — como
critério de merge, isso é um fiscal instável, fonte nova de flakiness num repositório cujo
argumento inteiro é que verde e vermelho significam alguma coisa.

O cache é aprovado pela **propriedade funcional**:

- a chave inclui o lockfile e a versão do runtime;
- a restauração é observável no log (`cache_hit`);
- falha de restore **nunca** vira artefato de fiscal — o hash recusa antes;
- o CI permanece correto em cache miss.

Ganho de tempo é **observabilidade**. Sem ganho após duas janelas de medição, abre-se CP de remoção
ou ajuste — não um vermelho automático.

## Paridade com integridade

`harness/local_validate.sh` instala do **mesmo** `requirements-ci.txt` que o CI, com
`--require-hashes`, e roda os **mesmos** comandos. Sem os hashes, um cache poderia esconder
dependência adulterada, e uma resolução local diferente produziria um verde que o CI limpo
contradiz.

### O custo declarado: plataforma

`--require-hashes` fixa **artefatos**, e wheel é específico de plataforma. `requirements-ci.txt` é
gerado para o que o CI usa: **Linux x86_64, CPython 3.11**.

Em outra plataforma a instalação **falha explicitamente**. Isso é o comportamento certo — a
alternativa seria cair para outra resolução em silêncio, que é a divergência exata que o lockfile
existe para impedir. O script diz o que fazer quando isso acontece.

Regenerar o lock (na plataforma do CI):

```bash
pip download --dest /tmp/lock "jsonschema>=4" "pyyaml>=6" "pytest>=8"
# para cada wheel: nome==versão + sha256 do arquivo
```

Containerização por digest fica como CP posterior, **condicionada a divergência medida**.

## Erros acionáveis

Todo achado diz o que fazer. `Findings.add` aplica um mapa **origem → remediação** quando o
chamador não traz algo mais específico — um mapa, não 49 repetições, porque a lista mantida à mão
deriva na primeira adição esquecida.

**O fiscal sugere o comando; jamais o executa** (fronteira do R-01). Um fiscal que conserta o que
acusa é juiz e parte.

## O checklist não é trava

`ci/pr_checklist.py` deriva de `stages.yaml` o que o PR aciona. Não reprova, e não entra em
`validate_all.py`: um checklist que reprovasse viraria o nono fiscal, sem política e sem teste de
mordida.

Fiscalizado por: `.github/workflows/governance.yml` (chave de cache + `--require-hashes`), `harness/local_validate.sh`, `ci/harness_lib.py` (REMEDIACAO_POR_ORIGEM)
Declarado em: `harness/change-proposals/CP-028-velocidade-e-paridade-local.yaml`, `architecture/adr/ADR-023-duracao-de-ci-nunca-e-gate.md`
Falha como: lockfile sem hash ⇒ asserção ADR-023-A2 vermelha; instalação sem `--require-hashes` ⇒ ADR-023-A3 vermelha.
