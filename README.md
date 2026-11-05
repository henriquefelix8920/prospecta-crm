# Prospecta CRM

CRM de prospecção com captura experimental de fichas públicas do Google Maps usando Playwright.

## Deploy gratuito

Conecte este repositório ao Render e selecione o Blueprint `render.yaml`. O serviço será criado no plano Free.

## Limitações

- A captura depende da interface pública do Google Maps, que pode mudar, bloquear acessos ou apresentar CAPTCHA; não há garantia de extração de todos os campos.
- Cada busca aceita até 20 resultados.
- SQLite no plano gratuito pode ser efêmero. Exporte CSV frequentemente; persistência confiável pode exigir recurso pago.
- Respeite os termos aplicáveis e a legislação de proteção de dados ao usar os contatos.

## Desenvolvimento local

`pip install -r requirements.txt && playwright install chromium && uvicorn app:app --reload`
