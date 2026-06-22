# Mailganer API MCP

MCP-сервер для **управления документацией** [REST API Mailganer](https://mailganer.com/documentation/api/).

Кэширует страницы документации и Postman-коллекцию локально в `docs/` и даёт ассистенту инструменты для поиска, синхронизации и проверки изменений. Live-вызовы API — не основной сценарий (есть заготовка `mailganer_client.py` на будущее).

## Структура

```
mailganer-api-mcp/
├── docs/
│   ├── overview.md          # авторизация, лимиты, пагинация
│   ├── api-index.json       # каталог всех страниц
│   ├── sitemap-pages.json   # страницы из sitemap.xml
│   ├── postman-index.json   # индекс Postman-запросов
│   ├── crosslinks.json      # связи docs ↔ Postman
│   ├── manual-crosslinks.json  # ручные связи и пояснения для «дырок»
│   ├── endpoints/           # JSON по каждой странице API
│   └── postman/             # Postman collection JSON
├── docs_kb.py               # логика KB: поиск, sync, diff
├── scripts/
│   ├── sync-api-docs.py     # парсер документации (sitemap + menu)
│   └── sync-postman.py      # синхронизация Postman-коллекции
└── server.py                # MCP-сервер
```

## Быстрый старт

```bash
cd mailganer-api-mcp
chmod +x setup.sh
./setup.sh .
```

Reload MCP в Cursor: **Settings → MCP → Reload**.

Или в чате: **«установи mailganer api docs»** / **«обнови документацию mailganer»**.

### Переменные окружения (`.env.api`)

```env
MAILGANER_API_KEY=your_api_key
MAILGANER_API_BASE_URL=https://mailganer.com/api
POSTMAN_API_KEY=PMAK-your_postman_api_key
```

- **MAILGANER_API_KEY** — раздел **Настройки аккаунта** в личном кабинете Mailganer (для live-вызовов API)
- **POSTMAN_API_KEY** — [Postman → Settings → API keys](https://go.postman.co/settings/me/api-keys)

### MCP-серверы

| Сервер | Назначение |
|---|---|
| `mailganer-api` | Локальный кэш документации Mailganer API |
| `postman` | Ваши workspace, коллекции и запросы в Postman |

Режим Postman MCP по умолчанию: `--code`. Чтобы сменить (`--minimal`, `--full`), отредактируйте `.cursor/postman-mcp.sh`.

## MCP-инструменты

| Инструмент | Описание |
|---|---|
| `get_doc_status` | Статус кэша: дата sync, кол-во страниц, ошибки |
| `sync_documentation` | Обновить docs с сайта (`all` / `api` / `postman`) |
| `list_api_docs` | Список страниц, фильтр по категории |
| `search_api_docs` | Полнотекстовый поиск по кэшу |
| `get_api_endpoint_doc` | Страница docs **+ связанные Postman-запросы** |
| `get_linked_postman_request` | Postman-запрос **+ связанные страницы docs** |
| `rebuild_doc_crosslinks` | Пересобрать `docs/crosslinks.json` |
| `list_crosslink_gaps` | Список «дырок» без связи + пояснения |
| `check_doc_page` | Сравнить кэш с live-сайтом, показать diff |
| `get_api_overview` | Обзор: auth, лимиты, пагинация |
| `search_postman` | Поиск по Postman-коллекции |
| `get_postman_request` | Запрос Postman по имени или path |

## Обновить документацию вручную

```bash
python3 scripts/sync-all-docs.sh
```

или по отдельности:

```bash
python3 scripts/sync-api-docs.py
python3 scripts/sync-postman.py
python3 scripts/build-crosslinks.py
```

## CI: автоматический sync

Workflow [`.github/workflows/sync-docs.yml`](.github/workflows/sync-docs.yml):

| Триггер | Когда |
|---|---|
| `schedule` | Каждый понедельник, 06:00 UTC |
| `workflow_dispatch` | Вручную: GitHub → Actions → Sync API docs → Run workflow |

Если документация на сайте изменилась, workflow создаёт PR `automation/sync-docs` с обновлённым `docs/`.

После merge PR локально: `git pull` или `./setup.sh .` для обновления кэша.

**Настройка репозитория (один раз):** Settings → Actions → General → Workflow permissions → *Read and write* и включить **Allow GitHub Actions to create and approve pull requests**. Без этого workflow не сможет открыть PR.

## Источники

| Источник | URL | Скрипт |
|---|---|---|
| Sitemap | https://mailganer.com/sitemap.xml | `sync-api-docs.py` |
| Меню API | https://mailganer.com/documentation/api/ | `sync-api-docs.py` (fallback) |
| Postman | https://documenter.getpostman.com/view/23131434/VUxPvnhA | `sync-postman.py` |

## Ручные связи (`manual-crosslinks.json`)

Автоматический матчинг не покрывает всё: разные пути (`/api/auth/` vs `/api/v2/auth/`), несколько способов вызова, методы без отдельной doc-страницы.

Файл `docs/manual-crosslinks.json`:
- `doc_to_postman` — явные связи slug → имена Postman-запросов
- `doc_notes` — пояснение, почему у страницы нет Postman (webhook, нет в коллекции)

После правок: `python3 scripts/build-crosslinks.py`  
Проверить «дыры»: MCP-инструмент `list_crosslink_gaps`.

## Авторизация API (справка)

- **v1** — `api_key` в теле запроса
- **v2** — заголовок `Authorization: CodeRequest {{api_key}}`
- Лимит: **500 запросов/мин**
