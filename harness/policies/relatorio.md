# O relatório do repositório: derivado, genérico e sem publicação por conta própria

O relatório é a vista de leitura do que hoje exige abrir 28 YAMLs e rodar onze fiscais. Ele existe
porque acompanhar este repositório sem tradução manual era impossível — e nasce genérico, então
serve todo derivado pelo mesmo motivo que `ci/orient.py` serve.

Três regras o definem, e as três são estruturais.

## 1. Ele não contém a informação, ele a deriva

Nenhuma lista escrita à mão dentro de `ci/generate_report.py`. Nenhum identificador literal. Nenhum
contador escrito na tela: todo número é `len()` da coleção real, lida do caminho declarado.

A razão não é elegância. Uma segunda descrição do repositório deriva da primeira **em silêncio** e
com aparência de documentação cuidadosa — e o repositório já tem a prova: `CLAUDE.md` afirma "as
treze etapas" enquanto `harness/stages.yaml` declara **catorze**. O texto passou a mentir na etapa
que alguém acrescentou sem reler a prosa, e nada o fiscalizava.

O relatório é a tela mais lida do repositório. Se ele restatar contadores, multiplica esse defeito
por vinte — e a armadilha é auto-referente: acrescentar este próprio gerador a `_steps()` mudou o
número de fiscais. Um número escrito na tela nasceria errado no primeiro commit.

## 2. Nenhum alvo é especial

Zero nomes de negócio, zero nomes de derivado, zero identificadores literais. Tudo isso é **dado**,
e mora nos YAML. O teste que prova não é de estilo: o gerador rodado contra um repositório sem o
negócio de exemplo produz relatório **vazio e coerente**, exit 0 — não um traceback, não uma tela
com buracos.

E o vazio tem três estados, que nunca se pintam iguais:

| Estado | Significa | Como se distingue |
|---|---|---|
| `declarado vazio` | o diretório existe e não há nada | afirmação do metadado |
| `ainda não ingerido` | o caminho não existe | trabalho pendente |
| `não consegui ler` | fonte ilegível | **exit 2**, nunca 0 |

Pintá-los igual é a família de defeito da CP-040: "nenhum" e "não sei olhar" saindo iguais é o
estado em que alguém avança achando que não há trabalho. Num derivado recém-criado — que é quem
mais abre esta tela — quase tudo cai no segundo caso.

## 3. O gerador nunca publica, e o inventário nunca sai em claro por padrão

Publicar é passo de workflow que alguém liga deliberadamente. Esta política **não liga nenhum**.

Quando o destino for público, `--redigir` é **obrigatório**: os campos do inventário de dado pessoal
viram contagens. No molde o inventário está vazio; num derivado ele traz finalidades, campos e bases
legais do alvo. Um HTML estático publicado com isso não vaza o dado do titular — vaza o **mapa de
onde ele está**, que é pior, porque é o que se procura primeiro.

Deixar `--redigir` como opção de fase dois seria escolher o default inseguro exatamente para o caso
que mais importa.

## Decisões declaradas que este documento fixa

**Fontes tipográficas.** O protótipo usa Caprasimo e Figtree via Google Fonts. O artefato **não as
carrega**: um laudo de auditoria que depende de rede para renderizar é um laudo que some quando a
rede some. A escolha é o fallback `system-ui`, e a tipografia degrada offline de propósito.

**Sem estado no navegador.** Sem `localStorage`, sem cookie, sem telemetria. Um relatório de
auditoria que guarda estado do leitor passa a ter, ele próprio, um inventário de dado a declarar.

**Sem SHA de commit embutido.** A procedência é o `sources_digest` — o digest do conteúdo de todas as
fontes. Embutir o `HEAD` tornaria o artefato diferente a cada commit: gera, commita, o `HEAD` muda,
o `--check` reprova, regenera, e a trava vira o ruído que as pessoas acabam desligando. O digest é
determinístico e mais preciso: dois commits que não tocam metadado têm o mesmo digest, e é isso que
se quer comparar.

**Sem executar fiscais por dentro.** `validate_all` chama este gerador com `--check`; se ele
chamasse `validate_all`, o ciclo se fecharia. O relatório mostra o laudo da **última** execução, lido
de `harness/reports/`, **com a data**. Número velho rotulado é honesto; número velho sem rótulo não é.

Fiscalizado por: `ci/generate_report.py::main`; `tests/governance/test_relatorio_bites.py`.
Declarado em: `harness/change-proposals/CP-045-relatorio-derivado.yaml`; `architecture/adr/index.yaml` → `ADR-031`; `harness/stages.yaml` → `STAGE-DOCS`.
Falha como: artefato desatualizado ou editado à mão ⇒ `--check` exit 1 com os caminhos divergentes; fonte ilegível ou dependência ausente ⇒ exit 2 (`FISCAL_CEGO:`), nunca 0; identificador literal no gerador ⇒ achado da asserção `ADR-031-A3`; leitor de YAML paralelo ⇒ achado da asserção `ADR-031-A2`.
