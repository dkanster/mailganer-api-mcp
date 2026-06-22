# Mailganer API MCP

MCP-сервер и локальная база знаний по [REST API Mailganer](https://mailganer.com/documentation/api/).

Проект кэширует документацию по всем endpoint-страницам и даёт ассистенту инструменты для поиска и чтения справки. Прямые вызовы API — через `mailganer_client.py` (базовый HTTP-клиент).

## Структура

```
mailganer-api-mcp/
├── docs/
│   ├── overview.md          # авторизация, лимиты, пагинация
│   ├── api-index.json       # каталог всех страниц документации
│   ├── sitemap-pages.json   # страницы из sitemap.xml
│   ├── postman-index.json   # индекс запросов Postman-коллекции
│   ├── endpoints/           # JSON по каждому методу API
│   └── postman/             # Postman collection JSON
├── scripts/
│   ├── sync-api-docs.py     # парсер документации (sitemap + menu)
│   └── sync-postman.py      # синхронизация Postman-коллекции
├── server.py                # MCP-сервер (поиск по KB)
├── mailganer_client.py        # HTTP-клиент Mailganer API
└── config.py                # чтение .env.api
```

## Быстрый старт

```bash
cd mailganer-api-mcp
chmod +x setup.sh
./setup.sh .
```

`setup.sh` создаёт venv, `.env.api`, launcher `.cursor/api-mcp.sh`, `.cursor/mcp.json` и синхронизирует документацию.

### Переменные окружения (`.env.api`)

```env
MAILGANER_API_KEY=your_api_key
MAILGANER_API_BASE_URL=https://mailganer.com/api
```

API-ключ — в разделе **Настройки аккаунта** личного кабинета Mailganer.

### Обновить документацию

```bash
python3 scripts/sync-api-docs.py
python3 scripts/sync-postman.py
```

## MCP-инструменты

| Инструмент | Описание |
|---|---|
| `search_api_docs` | Поиск по кэшированной документации |
| `get_api_endpoint_doc` | Полная справка по slug (например `email-add`) |
| `get_api_overview` | Обзор: auth v1/v2, лимиты, пагинация |

## Авторизация API

- **v1** — `api_key` в теле запроса
- **v2** — заголовок `Authorization: CodeRequest {{api_key}}`

Лимит: **500 запросов/мин** (HTTP 429 при превышении).

## Источники

| Источник | URL | Скрипт |
|---|---|---|
| Документация (sitemap) | https://mailganer.com/sitemap.xml | `sync-api-docs.py` |
| Документация (меню API) | https://mailganer.com/documentation/api/ | `sync-api-docs.py` (fallback) |
| Postman-коллекция | https://documenter.getpostman.com/view/23131434/VUxPvnhA | `sync-postman.py` |

Sitemap — основной список страниц; пункты меню на `/documentation/api/` дополняют его, если страницы нет в sitemap.
