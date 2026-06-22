---
name: manage-api-docs
description: >-
  Управление кэшем документации Mailganer REST API. Используй при запросах
  «обнови документацию mailganer», «найди в api docs», «что изменилось в docs»,
  «sync api docs», «проверь страницу email-add».
---

# Управление документацией Mailganer API

MCP-сервер **mailganer-api** — для работы с **локальным кэшем** документации, не для live-вызовов API.

## Установка

```bash
git clone https://github.com/dkanster/mailganer-api-mcp.git
cd mailganer-api-mcp
./setup.sh .
```

Reload MCP в Cursor: **Settings → MCP → Reload**.

`MAILGANER_API_KEY` для управления документацией **не нужен** — только для будущих live-вызовов API.

`POSTMAN_API_KEY` нужен для MCP-сервера **postman** (коллекции и workspace в вашем аккаунте). Локальный кэш Postman (`docs/postman/`) синхронизируется из публичной коллекции и работает без ключа.

## Типовые сценарии

### Обновить весь кэш

Инструмент `sync_documentation` с `target: "all"`.

Или в терминале:

```bash
python3 scripts/sync-api-docs.py
python3 scripts/sync-postman.py
```

### Статус кэша

`get_doc_status` — когда последний sync, сколько страниц, ошибки, Postman.

### Найти метод

1. `search_api_docs` — по тексту страниц (параметры, примеры, заголовки)
2. `search_postman` — по Postman-коллекции
3. `get_api_endpoint_doc` — страница docs **вместе с Postman-запросами**
4. `get_linked_postman_request` — Postman-запрос **вместе со страницами docs**

### Проверить, изменилась ли страница на сайте

`check_doc_page` с slug — сравнивает кэш с live-версией и показывает diff.

### «Дыры» в связях docs ↔ Postman

`list_crosslink_gaps` — что не связано и почему (`doc_notes` в `docs/manual-crosslinks.json`).

Ручные связи правятся в `docs/manual-crosslinks.json`, затем `rebuild_doc_crosslinks`.

### Список страниц по разделу

`list_api_docs` с фильтром `category`, например «подписчик», «триггер», «рассылк».

## Источники данных

| Источник | URL |
|---|---|
| Sitemap | https://mailganer.com/sitemap.xml |
| Меню API | https://mailganer.com/documentation/api/ |
| Postman | https://documenter.getpostman.com/view/23131434/VUxPvnhA |

Sitemap содержит мало страниц — основной список endpoint-страниц берётся из меню.

## Когда предлагать sync

- Пользователь говорит, что на сайте docs уже другие
- `check_doc_page` показал изменения
- Давно не обновляли (`synced_at` старше недели)
