# Radar Licita Ti.Net

Sistema interno para monitoramento de licitações em São Francisco do Conde, Cachoeira, Santo Amaro e Saubara.

## Recursos

- Coleta de oportunidades na BLL Compras
- Classificação por aderência ao negócio da Ti.Net
- Separação entre oportunidades prioritárias e outras oportunidades
- Extração de valor do processo
- Link direto para a licitação
- Notificações por e-mail
- Notificações por WhatsApp via Evolution API
- Coleta automática
- Controle de status: Nova, Notificada, Visualizada, Favorita e Descartada

## Execução local

Rodar localmente:

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py

Acesse: http://localhost:8080

Nunca envie .env, banco de dados, QR Code, tokens ou senhas para o GitHub.
