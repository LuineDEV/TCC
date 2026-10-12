# Organizador de E-mails Desktop

Protótipo acadêmico para TCC com foco em classificação local de e-mails usando NLP, TF-IDF, Scikit-Learn e armazenamento local.

## Funcionalidades

- Importação de e-mails por CSV.
- Treinamento de modelo supervisionado com TF-IDF e Regressão Logística.
- Classificação nas categorias `Urgente`, `Trabalho` e `Pessoal`.
- Interface desktop em Python com CustomTkinter.
- Persistência em MySQL local quando configurado.
- Cache JSON local para demonstração quando o MySQL ainda não estiver disponível.
- Filtros por categoria e correção manual da classificação.
- Retreinamento com os e-mails salvos localmente, incluindo correções manuais.

## Importação do Gmail

O botão **Importar do Gmail** usa a janela do Google Chrome que já está aberta e autenticada pelo usuário. Antes de iniciar a leitura, deixe o Gmail aberto na Caixa de Entrada, com a janela maximizada e zoom em 100%.

A coleta abre até 10 mensagens da primeira página da Caixa de Entrada, copia o conteúdo visível e classifica automaticamente os registros importados. Durante a coleta, não use o mouse ou o teclado. O protótipo usa automação assistida de tela e não envia, exclui ou arquiva mensagens.

## Estrutura do CSV

Para importar e-mails, o arquivo CSV deve conter pelo menos:

```csv
sender,subject,body,category
usuario@email.com,Assunto da mensagem,Texto do e-mail,Trabalho
```

Para importação, `category` é opcional. Quando a coluna `category` existe, ela entra como categoria inicial do e-mail.

## Aprendizado com correções

O botão **Treinar modelo** usa os e-mails que já estão salvos na aplicação. Assim, o fluxo fica:

```text
Importar e-mails -> corrigir categorias na tela -> Treinar modelo -> modelo salvo
```

As categorias corrigidas manualmente entram na próxima rodada de treinamento. O novo modelo é salvo em `models/email_classifier.joblib` e será usado nas próximas execuções do aplicativo.

## Configuração do MySQL

1. Crie um arquivo `.env` a partir de `.env.example`.
2. Ajuste usuário, senha, host, porta e nome do banco.
3. O sistema cria automaticamente o banco e as tabelas ao iniciar, se o usuário tiver permissão.

Exemplo:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=sua_senha
DB_NAME=email_classifier_tcc
```

Se o MySQL não estiver disponível, o aplicativo entra em modo de demonstração usando `cache/emails_cache.json`.

## Como executar

```bash
python -m email_classifier_app.main
```

Na primeira execução, o modelo é treinado automaticamente com `data/sample_emails.csv` se ainda não existir arquivo em `models/email_classifier.joblib`.

## Escopo acadêmico

Este projeto é um protótipo de classificação e visualização local de e-mails. Ele não pretende substituir um cliente completo de e-mail, nem implementar resposta automática ou resumo de mensagens como funcionalidades principais.
