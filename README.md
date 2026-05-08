# Здравствуйте, Крякен!

## Возможности

- Проверяет логин пользователя через School21 Open API
- Отправляет заявку модераторам с карточкой и кнопками
- Модератор одобряет или отклоняет заявку
- После одобрения пользователь получает уникальную одноразовую ссылку
- Банлист: заблокированные пользователи не могут взаимодействовать с ботом

### Развёртывание

```bash
git clone https://github.com/darkneeed/duck_quack_bot.git
cd duck_quack_bot
cp .env.example .env # Заполните переменные
docker compose up -d
```

## Конфигурация

### `.env`

| Переменная | Обязательная | Описание |
|---|---|---|
| `BOT_TOKEN` | ✅ | Токен бота от @BotFather |
| `ADMIN_IDS` | ✅ | ID модераторов через запятую |
| `MODERATION_CHAT_ID` | ✅ | ID чата для карточек модерации |
| `COMMUNITY_CHAT_ID` | ✅ | ID чата, куда выдаются инвайты |
| `S21_API_USERNAME` | ✅ | Логин для School21 API |
| `S21_API_PASSWORD` | ✅ | Пароль для School21 API |
| `S21_CAMPUS_ID` | ✅ | ID кампуса |
| `RC_BASE_URL` | ✅ | Базовый URL Rocket.Chat |
| `RC_USER_ID` | ✅ | Сервисный user id Rocket.Chat |
| `RC_AUTH_TOKEN` | ✅ | Auth token Rocket.Chat |
| `DB_PATH` | ❌ | Путь к SQLite-файлу (по умолчанию `data/bot.db`) |

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

## Предварительные требования для бота

1. Бот должен быть **администратором** в `COMMUNITY_CHAT_ID` с правом создавать инвайт-ссылки.
2. Бот должен быть **администратором** в `MODERATION_CHAT_ID` с правом отправлять сообщения в топик.
3. Для топиков: в боте нужно включить `message_thread_id` (передаётся автоматически).
