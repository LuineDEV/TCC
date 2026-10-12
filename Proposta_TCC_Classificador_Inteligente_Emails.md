# Proposta de TCC

## Dados Gerais

- **Instituição:** Universidade Veiga de Almeida (UVA)
- **Curso:** Ciência da Computação
- **Aluno:** Luis Felipe Costa Pedro
- **Orientador:** Prof. Rogério Mandelli
- **Local e ano:** Rio de Janeiro, 2026

## 1. Título do TCC

**Classificador Inteligente de E-mails Desktop com Processamento de Linguagem Natural e Aprendizado de Máquina: uma abordagem local orientada à privacidade**

Título alternativo, mais curto:

**Classificação Inteligente de E-mails em Aplicação Desktop com NLP e Processamento Local**

## 2. Tema Delimitado

O trabalho tem como tema o desenvolvimento de uma aplicação desktop para classificação automática de e-mails por meio de técnicas de Processamento de Linguagem Natural (NLP) e Aprendizado de Máquina, com armazenamento local em banco de dados MySQL.

A delimitação do projeto concentra-se na classificação de mensagens em categorias predefinidas, como **Urgente**, **Trabalho** e **Pessoal**, utilizando vetorização TF-IDF e algoritmos supervisionados da biblioteca Scikit-Learn. O sistema deverá priorizar o processamento local dos dados, adotando o princípio de Privacidade por Design.

Funcionalidades como sugestão automática de respostas e resumo de e-mails poderão ser discutidas como possibilidades futuras, mas não constituem o núcleo obrigatório da proposta.

## 3. Problema de Pesquisa

Com o aumento do volume de mensagens recebidas diariamente, muitos usuários enfrentam dificuldades para identificar rapidamente e-mails relevantes, urgentes ou relacionados a diferentes contextos de uso. Soluções comerciais de e-mail frequentemente dependem de processamento em nuvem, o que pode gerar preocupações relacionadas à privacidade, confidencialidade e controle sobre dados sensíveis.

Diante desse contexto, o problema de pesquisa pode ser formulado da seguinte forma:

**Como desenvolver uma aplicação desktop capaz de classificar automaticamente e-mails por meio de técnicas de NLP e Aprendizado de Máquina, mantendo o processamento e o armazenamento dos dados no ambiente local do usuário?**

## 4. Hipótese ou Pergunta Norteadora

Hipótese:

**A utilização de técnicas clássicas de NLP, como limpeza textual, tokenização e vetorização TF-IDF, combinadas com algoritmos supervisionados de classificação, pode viabilizar uma aplicação desktop capaz de organizar e-mails em categorias relevantes, com desempenho satisfatório e sem depender de processamento em nuvem para dados sensíveis.**

Pergunta norteadora:

**De que forma um sistema desktop com processamento local pode auxiliar o usuário na triagem de e-mails, garantindo usabilidade, transparência e maior controle sobre seus dados?**

## 5. Objetivo Geral

Desenvolver um protótipo de software desktop para classificação inteligente de e-mails, utilizando Processamento de Linguagem Natural e Aprendizado de Máquina, com armazenamento local em MySQL e foco em privacidade, usabilidade e organização das mensagens.

## 6. Objetivos Específicos

- Estudar conceitos de Processamento de Linguagem Natural aplicados à classificação de textos.
- Investigar algoritmos supervisionados adequados para classificação de e-mails.
- Implementar um pipeline de pré-processamento textual, incluindo limpeza, normalização, tokenização e remoção de termos irrelevantes.
- Aplicar vetorização TF-IDF para transformar o conteúdo textual dos e-mails em representações numéricas.
- Treinar e avaliar modelos de classificação com Scikit-Learn.
- Desenvolver uma interface desktop simples para visualização dos e-mails classificados.
- Armazenar localmente mensagens, categorias, resultados de classificação, cache e logs em banco de dados MySQL.
- Avaliar o desempenho do classificador por meio de métricas como acurácia, precisão, revocação e F1-score.
- Analisar os limites da abordagem local em relação à privacidade, desempenho e qualidade da classificação.

## 7. Justificativa Acadêmica, Técnica e Social

### Justificativa Acadêmica

O projeto se justifica academicamente por integrar conceitos estudados na Ciência da Computação, como Processamento de Linguagem Natural, Aprendizado de Máquina, engenharia de software, banco de dados e interfaces desktop. A proposta permite aplicar técnicas de classificação textual em um problema prático e recorrente, contribuindo para a formação do estudante por meio do desenvolvimento de uma solução computacional completa.

### Justificativa Técnica

Do ponto de vista técnico, a proposta explora uma arquitetura local, em que o processamento dos e-mails ocorre na própria máquina do usuário. Essa escolha permite discutir alternativas a sistemas baseados exclusivamente em nuvem, além de avaliar a viabilidade de algoritmos clássicos de machine learning, como Naive Bayes, Regressão Logística ou Support Vector Machine, em tarefas de classificação de texto.

O uso de TF-IDF e Scikit-Learn torna o projeto viável para graduação, pois permite construir um classificador funcional sem exigir infraestrutura complexa, modelos generativos de grande porte ou processamento intensivo.

### Justificativa Social

Socialmente, o projeto aborda a necessidade de organização da informação e de proteção de dados pessoais. E-mails podem conter informações profissionais, financeiras, acadêmicas e pessoais. Assim, uma ferramenta local, transparente e controlada pelo usuário pode contribuir para maior autonomia digital e melhor gestão da comunicação cotidiana.

## 8. Metodologia do Projeto

A metodologia adotada será de natureza aplicada, com abordagem experimental e desenvolvimento de protótipo.

O trabalho será desenvolvido nas seguintes etapas:

1. **Pesquisa bibliográfica:** estudo de NLP, classificação de textos, TF-IDF, algoritmos supervisionados, privacidade por design e ferramentas desktop em Python.
2. **Levantamento de requisitos:** definição das funcionalidades essenciais, restrições técnicas e critérios de avaliação.
3. **Definição da base de dados:** utilização de conjunto de dados público de e-mails ou mensagens textuais, complementado por dados de teste simulados, respeitando critérios éticos e de privacidade.
4. **Pré-processamento textual:** limpeza do texto, conversão para minúsculas, remoção de pontuação, stopwords e possível lematização.
5. **Vetorização e treinamento:** aplicação de TF-IDF e treinamento de modelos supervisionados com Scikit-Learn.
6. **Avaliação do modelo:** comparação de desempenho por métricas como acurácia, precisão, revocação e F1-score.
7. **Desenvolvimento da aplicação desktop:** criação da interface para listar, filtrar e visualizar e-mails classificados.
8. **Persistência local:** modelagem e implementação do banco MySQL para armazenar e-mails, categorias, classificações, logs e configurações.
9. **Testes funcionais:** verificação dos fluxos principais do sistema, incluindo importação, classificação, visualização e consulta.
10. **Análise dos resultados:** discussão sobre desempenho, limitações, privacidade e possibilidades de evolução.

## 9. Tecnologias Utilizadas e Justificativa

| Tecnologia | Finalidade | Justificativa |
|---|---|---|
| Python | Linguagem principal | Possui amplo ecossistema para IA, NLP, banco de dados e desenvolvimento desktop. |
| CustomTkinter ou PyQt6 | Interface gráfica desktop | Permite criar uma interface funcional para visualização e gerenciamento dos e-mails classificados. |
| NLTK ou SpaCy | Processamento de Linguagem Natural | Oferece recursos para tokenização, stopwords, normalização e tratamento textual. |
| Scikit-Learn | Aprendizado de Máquina | Biblioteca consolidada para classificação supervisionada, treinamento e avaliação de modelos. |
| TF-IDF | Vetorização de texto | Técnica adequada e viável para representar textos em modelos clássicos de classificação. |
| MySQL | Armazenamento local | Banco relacional robusto para persistir mensagens, categorias, histórico e configurações. |
| Pandas | Manipulação de dados | Facilita leitura, tratamento e organização de datasets durante treinamento e avaliação. |
| IMAP | Possível coleta de e-mails | Pode ser usado para importar mensagens de contas compatíveis, desde que respeitadas as limitações de autenticação. |
| Logs locais | Auditoria e depuração | Permitem registrar operações importantes sem envio de dados sensíveis para servidores externos. |

## 10. Escopo do Sistema

### O que será feito

- Desenvolvimento de um protótipo desktop em Python.
- Importação de e-mails a partir de base local, arquivos ou fonte controlada para testes.
- Possível integração IMAP em escopo limitado, caso a autenticação do provedor permita.
- Pré-processamento do conteúdo textual dos e-mails.
- Classificação automática em categorias predefinidas.
- Armazenamento local em MySQL.
- Tela para visualização dos e-mails e suas respectivas categorias.
- Filtros simples por categoria.
- Registro local de logs e resultados de classificação.
- Avaliação do modelo com métricas de classificação.

### O que não será feito

- Não será desenvolvido um cliente de e-mail completo para envio e recebimento contínuo de mensagens.
- Não será implementado processamento em nuvem de dados sensíveis.
- Não será obrigatória a integração completa com Gmail, Outlook ou outros provedores que exijam OAuth2 complexo.
- Não será foco do TCC a criação de um modelo generativo de linguagem.
- Sugestão automática de respostas e resumo de e-mails não serão funcionalidades principais; poderão ser apresentadas como extensões futuras.
- Não será garantida classificação perfeita para todos os tipos de e-mail, especialmente mensagens muito curtas, ambíguas ou em formato HTML complexo.

## 11. Requisitos Funcionais e Não Funcionais

### Requisitos Funcionais

- RF01: O sistema deve permitir importar ou carregar e-mails para classificação.
- RF02: O sistema deve extrair o conteúdo textual relevante das mensagens.
- RF03: O sistema deve aplicar pré-processamento textual aos e-mails.
- RF04: O sistema deve classificar e-mails em categorias predefinidas, como Urgente, Trabalho e Pessoal.
- RF05: O sistema deve permitir visualizar a lista de e-mails classificados.
- RF06: O sistema deve permitir filtrar e-mails por categoria.
- RF07: O sistema deve armazenar localmente e-mails, categorias e resultados de classificação.
- RF08: O sistema deve registrar logs locais de operações relevantes.
- RF09: O sistema deve permitir reclassificar ou corrigir manualmente uma categoria, caso essa funcionalidade seja viável no protótipo.
- RF10: O sistema deve gerar indicadores básicos de desempenho do modelo durante a avaliação.

### Requisitos Não Funcionais

- RNF01: O processamento dos dados sensíveis deve ocorrer localmente.
- RNF02: O sistema deve possuir interface simples, clara e adequada a usuários não especialistas.
- RNF03: O banco de dados deve operar em ambiente local.
- RNF04: O sistema deve manter logs sem expor conteúdo sensível desnecessariamente.
- RNF05: O protótipo deve ser executável em computador pessoal com configuração comum.
- RNF06: O código deve ser organizado em módulos, separando interface, processamento, classificação e persistência.
- RNF07: O modelo deve ser avaliado com métricas adequadas para classificação de texto.
- RNF08: O sistema deve apresentar transparência mínima sobre a categoria atribuída, exibindo o resultado da classificação ao usuário.

## 12. Estrutura Sugerida dos Capítulos do TCC

### Capítulo 1 - Introdução

Apresentação do tema, contextualização, problema de pesquisa, hipótese ou pergunta norteadora, objetivos, justificativa e delimitação do trabalho.

### Capítulo 2 - Fundamentação Teórica

Discussão sobre Processamento de Linguagem Natural, classificação de textos, TF-IDF, algoritmos de Aprendizado de Máquina, aplicações de IA em e-mails, privacidade por design e armazenamento local.

### Capítulo 3 - Metodologia

Descrição do tipo de pesquisa, etapas de desenvolvimento, base de dados, critérios de avaliação, ferramentas utilizadas e estratégia de testes.

### Capítulo 4 - Desenvolvimento do Sistema

Apresentação da arquitetura, modelagem do banco de dados, pipeline de NLP, treinamento do classificador, interface desktop e principais fluxos do sistema.

### Capítulo 5 - Resultados e Discussão

Exposição dos testes realizados, métricas obtidas, análise dos resultados, comparação entre modelos e discussão sobre limitações.

### Capítulo 6 - Considerações Finais

Conclusão, contribuições do trabalho, dificuldades encontradas e sugestões para trabalhos futuros, como resumo automático e sugestão de respostas.

## 13. Cronograma Básico de Desenvolvimento

| Etapa | Mês 1 | Mês 2 | Mês 3 | Mês 4 | Mês 5 | Mês 6 |
|---|---|---|---|---|---|---|
| Pesquisa bibliográfica | X | X |  |  |  |  |
| Definição de requisitos e escopo | X | X |  |  |  |  |
| Escolha e preparação da base de dados |  | X | X |  |  |  |
| Desenvolvimento do pipeline de NLP |  |  | X | X |  |  |
| Treinamento e avaliação do classificador |  |  | X | X |  |  |
| Modelagem e implementação do MySQL |  |  |  | X |  |  |
| Desenvolvimento da interface desktop |  |  |  | X | X |  |
| Testes funcionais e ajustes |  |  |  |  | X | X |
| Escrita da monografia | X | X | X | X | X | X |
| Revisão final e apresentação |  |  |  |  |  | X |

## 14. Possíveis Riscos ou Limitações

- Dificuldade de obter uma base de e-mails rotulada em português com qualidade suficiente.
- Necessidade de utilizar datasets públicos em inglês ou dados simulados, o que pode limitar a generalização dos resultados.
- Variabilidade dos formatos dos e-mails, especialmente mensagens em HTML, assinaturas, anexos e textos muito curtos.
- Limitações de autenticação em provedores modernos, como Gmail e Outlook, que podem exigir OAuth2.
- Desempenho inferior em mensagens ambíguas ou que se encaixem em mais de uma categoria.
- Necessidade de ajustes no banco MySQL local para diferentes ambientes de execução.
- Escopo excessivo caso sejam incluídas funcionalidades generativas, como resumo e sugestão de resposta, antes da conclusão do classificador principal.

## 15. Trabalhos Correlatos e Temas para Pesquisa

Para fundamentar o TCC, recomenda-se pesquisar os seguintes temas:

- Classificação automática de e-mails e filtros de spam.
- Processamento de Linguagem Natural aplicado a textos curtos.
- Vetorização TF-IDF e modelos Bag-of-Words.
- Algoritmos Naive Bayes, Regressão Logística e Support Vector Machine para classificação textual.
- Avaliação de modelos de classificação com acurácia, precisão, revocação e F1-score.
- Privacidade por Design e proteção de dados pessoais.
- LGPD aplicada a sistemas que processam informações pessoais.
- Aplicações desktop em Python com CustomTkinter ou PyQt6.
- Sistemas offline-first e armazenamento local.
- Trabalhos sobre assistentes inteligentes de e-mail e organização automática de mensagens.

Referências iniciais que podem apoiar a fundamentação:

- BIRD, Steven; KLEIN, Ewan; LOPER, Edward. **Natural Language Processing with Python**. O'Reilly Media, 2009.
- CAVOUKIAN, Ann. **Privacy by Design: The 7 Foundational Principles**. Information and Privacy Commissioner of Ontario, 2009.
- PEDREGOSA, Fabian et al. **Scikit-learn: Machine Learning in Python**. Journal of Machine Learning Research, 2011.
- JURAFSKY, Daniel; MARTIN, James H. **Speech and Language Processing**.
- MANNING, Christopher D.; RAGHAVAN, Prabhakar; SCHÜTZE, Hinrich. **Introduction to Information Retrieval**. Cambridge University Press, 2008.

## Delimitação Recomendada para Apresentação ao Orientador

Recomenda-se apresentar o projeto como um **protótipo acadêmico de classificação local de e-mails**, e não como um cliente de e-mail completo. O núcleo avaliável do TCC deve ser:

- entrada de mensagens;
- pré-processamento textual;
- classificação automática;
- armazenamento local;
- visualização dos resultados;
- avaliação por métricas.

Dessa forma, o trabalho permanece viável para graduação, possui fundamentação técnica clara e evita dependência de serviços externos ou funcionalidades excessivamente amplas.
