# Painel de configuração — a tela deriva, ou não existe

O painel em `docs/configuracao/` responde *o que já está decidido antes de eu chegar?*: o
vocabulário fechado, a gramática dos identificadores, as combinações que os contratos tornam
inexpressáveis, o plano de controle, e o que um derivado herda travado versus o que nasce vazio.

É um **artefato derivado**, e a palavra carrega a política inteira: ele não guarda informação
alguma, ele a lê de `harness/schemas/` e da configuração no instante em que é gerado.

## Por que a regra aqui é mais dura que nas outras telas

Um dado velho às vezes é visivelmente velho. **Um vocabulário velho não é.**

Uma lista de valores escrita à mão dentro do gerador continuaria renderizando perfeita depois que
o contrato ganhasse um valor novo — sem erro, sem aviso, sem nada ficar vermelho — ensinando um
vocabulário que o repositório já não usa. É a segunda descrição do `ADR-014` na forma que não
quebra, e é o `RISK-ORIENT-001` no seu ponto de maior exposição.

Daí a regra, que não admite exceção pontual:

> **Nenhum valor de vocabulário, forma de identificador, valor travado ou contagem é literal em
> `ci/generate_config_report.py`.** Toda contagem é `len()` de coleção derivada — inclusive a de
> fiscais agregados, que mudou quando este próprio gerador entrou em `ci/validate_all.py`.

O gerador **prova isso a cada execução**: `_vocabulario_nao_esta_no_codigo` lê o próprio AST e
aborta se encontrar valor de vocabulário em posição de dado. Lê o AST, e não o texto, porque um
arquivo que fala *sobre* vocabulário contém as palavras do assunto em toda parte — inclusive nos
comentários que explicam por que ele não deve conter os valores. Procurar no texto cru seria a
próxima ocorrência da âncora-na-menção registrada em `conformance.md`.

**Quando a autoauditoria acusar, o conserto é renomear a string interna do gerador.** Nunca abrir
exceção para ela: lista de exceção é o buraco que este desenho existe para não ter.

## Deduplicação por ponteiro, jamais por valor

A mesma escala de rótulos aparece em vários contratos significando coisas diferentes — severidade
de asserção, criticidade de negócio, nível de risco de proposta. Fundi-las apagaria exatamente a
informação de que são escalas distintas, que é o que o leitor precisa ver.

## Os três estados de vazio

`declarado vazio` ≠ `ainda não ingerido` ≠ `não consegui ler`. Nunca são pintados iguais, e o
terceiro jamais sai como exit 0. Um contrato ilegível vira exit 2 com nome e motivo — nunca
"esse arquivo não tem valores", que faria a seção encolher em silêncio com a tela ainda bonita.

## Classificação fail-closed

O agrupamento temático dos contratos e o das variáveis negadas são as **únicas** decisões de
apresentação do gerador. Ambos falham fechado **nos dois sentidos**: contrato sem grupo e grupo
apontando para contrato que já não existe abortam com **exit 2** — não 1, porque exit 1 significa
"regenere", e regenerar não classifica um contrato novo.

## Offline, e a fonte que se aceita perder

O artefato abre de `file://` sem rede. O `@import` remoto do stylesheet é removido
**mecanicamente a cada geração** e conferido depois — nunca por edição à mão no arquivo copiado,
senão nada impede uma cópia futura de reintroduzi-lo.

**Escolha declarada:** as fontes do design system (Caprasimo, Figtree) **não** são embutidas. O
painel degrada para `system-ui` no texto e `ui-monospace` na tipografia literal. A degradação é
aceita porque a distinção que a tela realmente precisa — valor literal em monoespaçada, prosa em
proporcional — sobrevive a ela em qualquer plataforma moderna, e porque um painel que busca fonte
na rede some quando a rede some, em silêncio, já que a página ainda abre.

## Procedência por conteúdo, não por commit

O artefato conferido **não** embute o commit SHA. Embutir faria o `--check` reprovar para sempre:
o arquivo nasce num commit e é conferido no seguinte, então o valor mudaria sem que o conteúdo
mudasse. A procedência é `inputs_fingerprint` — impressão do conteúdo de tudo que foi lido —, e o
carimbo volátil vai para `harness/reports/config-report.json`, por onde nenhum fiscal caminha.

Fiscalizado por: `ci/generate_config_report.py::main`, `harness/schemas/config-report.schema.json`, `ci/validate_all.py`, `tests/governance/test_configuracao_bites.py`
Declarado em: `harness/change-proposals/CP-050-painel-de-configuracao.yaml`
Falha como: artefato divergente da árvore ⇒ `--check` sai 1; contrato ilegível, não classificado, ou valor de vocabulário transcrito no gerador ⇒ exit 2.
