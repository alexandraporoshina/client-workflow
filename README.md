# Client Workflow

Приватный переносимый marketplace-пакет для Codex. Он содержит ровно два навыка:

- `client-session-workflow` — разбор только проверенной транскрибации, подготовка к сессии и обзор подтверждённой динамики;
- `food-diary-analysis` — разбор одного явно выбранного дневника и нейтральный PDF для совместного просмотра.

## Границы

В репозитории нет клиентских данных, транскриптов, дневников, токенов, интеграций, хуков или фоновых процессов. Общие правила лежат в `plugins/client-workflow/_shared/client-project-contract.md`.

Навыки не диагностируют, не выдают рабочую гипотезу за факт и не превращают временную связь в причинную. Любая запись проходит шлюз `Черновик -> подтверждение -> запись`; Google Drive требует отдельного разрешения. PDF дневника принимает только нейтральные поля строгого JSON-контракта.

## Состав

```text
.agents/plugins/marketplace.json
plugins/client-workflow/
├── .codex-plugin/plugin.json
├── _shared/client-project-contract.md
└── skills/
    ├── client-session-workflow/
    └── food-diary-analysis/
```

`food-diary-analysis/scripts/render_diary_pdf.py` требует Python 3.10+ и пакет `reportlab`. Для проверки извлечённого PDF в тестах также используется `pypdf`.

## Установка из GitHub

Добавьте публичный marketplace и установите плагин:

```bash
codex plugin marketplace add alexandraporoshina/client-workflow --ref main
codex plugin add client-workflow@personal
```

Или вставьте в задачу Codex: `Установи плагин client-workflow из alexandraporoshina/client-workflow`. Никаких внешних ключей или авторизации пакет не запрашивает.

## Проверка

```bash
python3 /путь/к/plugin-creator/scripts/validate_plugin.py \
  plugins/client-workflow
python3 -m unittest tests/test_render_diary_pdf.py
```

Лицензия: MIT. См. [LICENSE](LICENSE).
