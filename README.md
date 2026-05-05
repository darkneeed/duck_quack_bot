# s21-auth-bot

Telegram-бот для верификации участников Школы 21.

## Возможности

- Проверяет логин пользователя через School21 Open API
- Отправляет заявку модераторам с карточкой и кнопками
- Модератор одобряет или отклоняет заявку (с необязательной причиной)
- После одобрения пользователь получает уникальную одноразовую ссылку
- После решения одного модератора кнопки у остальных деактивируются
- Банлист: заблокированные пользователи не могут взаимодействовать с ботом
- Администратор может из лички собрать пост в общий тред через `/post` или `/пост`

## Структура проекта

```
s21_bot/
├── main.py             # точка входа
├── config.py           # bootstrap-конфиг + runtime overrides
├── command_catalog.py  # единый каталог справки по командам
├── db/
│   ├── models.py       # схема БД и инициализация
│   ├── user_repo.py
│   ├── application_repo.py
│   ├── auth_attempt_repo.py
│   └── repo.py         # совместимый re-export старых импортов
├── handlers/
│   ├── auth.py         # /start, login, OTP, submit flow
│   ├── cabinet.py      # кабинет одобренного пользователя
│   ├── admin_users.py  # админские команды
│   ├── admin_callbacks.py
│   ├── admin.py        # совместимый router-composer
│   └── user.py         # совместимый router-composer
├── services/
│   ├── s21_api.py      # клиент School21 API (auth + participant lookup)
│   ├── invite.py       # генерация одноразовых ссылок
│   └── community_moderation.py
├── keyboards/
│   └── inline.py       # inline-клавиатуры
├── middlewares/
│   └── ban_check.py    # блокировка забаненных пользователей
└── utils/
    ├── states.py
    ├── helpers.py
    ├── profile.py      # общий рендер профиля
    └── telegram.py     # safe Telegram helpers
```

## Развёртывание

### Через Docker Compose (рекомендуется)

```bash
cp .env.example .env
# Заполните .env
docker compose up -d
```

### Локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Заполните .env
python -m s21_bot.main
```

## Конфигурация

### Bootstrap `.env`

| Переменная | Обязательная | Описание |
|---|---|---|
| `BOT_TOKEN` | ✅ | Токен бота от @BotFather |
| `ADMIN_IDS` | ✅ | ID модераторов через запятую |
| `MODERATION_CHAT_ID` | ✅ | ID чата для карточек модерации |
| `COMMUNITY_CHAT_ID` | ✅ | ID чата, куда выдаются инвайты |
| `S21_API_USERNAME` | ✅ | Логин для School21 API |
| `S21_API_PASSWORD` | ✅ | Пароль для School21 API |
| `S21_CAMPUS_ID` | ✅ | Числовой ID кампуса |
| `RC_BASE_URL` | ✅ | Базовый URL Rocket.Chat |
| `RC_USER_ID` | ✅ | Сервисный user id Rocket.Chat |
| `RC_AUTH_TOKEN` | ✅ | Auth token Rocket.Chat |
| `DB_PATH` | ❌ | Путь к SQLite-файлу (по умолчанию `data/bot.db`) |

### Runtime-настройки

- Все operational/branding-настройки теперь живут в таблице `bot_settings` и редактируются через `/admin`.
- При первом запуске бот автоматически backfill-ит legacy runtime-переменные из старого `.env` в `bot_settings`, если их там ещё нет.
- После backfill из `.env` можно удалить такие параметры, как `MODERATION_TOPIC_ID`, все `*_TOPIC_ID`, фичефлаги, интервалы, `CMD_*_SCOPE`, `SUPPORT_CONTACTS`, `SOCIAL_TRUST_PROJECT_IDS`, ссылки и брендинг.

## Схема БД

### `users`
| Поле | Описание |
|---|---|
| `tg_id` | Telegram user ID |
| `tg_name` | Имя из Telegram |
| `school_login` | Логин в Школе 21 |
| `coalition` | Трайб/коалиция |
| `application_date` | Дата первой заявки |
| `decision_date` | Дата решения |
| `status` | `pending` / `approved` / `rejected` / `banned` |
| `moderator_id` | TG ID модератора, принявшего решение |
| `comment` | Комментарий |
| `invite_link` | Выданная ссылка |
| `is_banned` | Флаг бана |

### `applications`
Хранит все заявки (в том числе повторные после отклонения).

## Предварительные требования для бота

1. Бот должен быть **администратором** в `COMMUNITY_CHAT_ID` с правом создавать инвайт-ссылки.
2. Бот должен быть **администратором** в `MODERATION_CHAT_ID` с правом отправлять сообщения в топик.
3. Для топиков: в боте нужно включить `message_thread_id` (передаётся автоматически).
