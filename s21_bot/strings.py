# ════════════════════════════════════════════════════════════════
# ОБЩИЕ
# ════════════════════════════════════════════════════════════════

BANNED                  = "🚫 Вы заблокированы."
ONLY_APPROVED           = "❌ Команда доступна только участникам сообщества."
COOLDOWN                = "⏳ Повторная подача заявки будет доступна через <b>{time}</b>.\nПопробуйте позже."
SESSION_EXPIRED         = "Сессия устарела. Начните заново /start."

# ════════════════════════════════════════════════════════════════
# /start — ПРИВЕТСТВИЕ И ПОТОК ЗАЯВКИ
# ════════════════════════════════════════════════════════════════

START_WELCOME = (
    "👋 Привет! Это бот для верификации участников основного обучения Школы 21.\n\n"
    "Пожалуйста, введите ваш <b>логин на платформе</b> "
    "(например: <code>nickname</code>).\n\n"
    "Отправляя свой ник, вы соглашаетесь с "
    "<a href='{rules_url}'>"
    "Правилами Чата</a> и обработкой персональных данных для верификации."
)  # {rules_url}
START_ALREADY_PENDING   = "⏳ Ваша заявка уже на рассмотрении. Мы уведомим вас о решении."
START_APPROVED_GREETING = "👋 Добро пожаловать, <b>{login}</b>!\n\nВыберите действие:"  # {login}
START_CHANGE_LOGIN_INFO = "ℹ️ Ваш текущий логин: <code>{login}</code>\n\nВведите новый логин или /cancel:"  # {login}

# ════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ ЛОГИНА
# ════════════════════════════════════════════════════════════════

LOGIN_INVALID_FORMAT    = "❌ Некорректный логин. Только буквы, цифры, - и _."
LOGIN_ALREADY_TAKEN     = "❌ Этот логин уже привязан к другому аккаунту."
LOGIN_CHECKING_S21      = "🔄 Проверяю логин в базе Школы 21…"
LOGIN_NOT_FOUND         = "❌ Логин <code>{login}</code> не найден в базе Школы 21.\n\nУбедитесь что вы ввели логин правильно."  # {login}
LOGIN_EXPELLED          = "❌ Логин <code>{login}</code> найден, но участник отчислен.\n\nЕсли вы считаете это ошибкой, обратитесь к модераторам."  # {login}
LOGIN_WRONG_CAMPUS      = "❌ Логин <code>{login}</code> зарегистрирован в другом кампусе.\n\nЭтот бот только для участников нашего кампуса."  # {login}
LOGIN_SUSPICIOUS_MANY   = "⚠️ За последние 30 мин использовано логинов: {count}\nПредыдущие: {prev}"  # {count}, {prev}
LOGIN_RATE_LIMITED      = "{user_msg}\n\n⛔️ Вы исчерпали <b>{max}/{max}</b> попыток."  # {user_msg}, {max}
LOGIN_ATTEMPTS_LEFT     = "{user_msg}\n\n📊 Попыток: <b>{used}/{max}</b>. Осталось: {remaining}."  # {user_msg}, {used}, {max}, {remaining}

# ════════════════════════════════════════════════════════════════
# РОКЕТ ЧАТ / OTP
# ════════════════════════════════════════════════════════════════

RC_CHECKING             = "🔄 Проверяю аккаунт в Rocket.Chat…"
RC_UNAVAILABLE          = "⚠️ Rocket.Chat временно недоступен. Попробуйте позже."
RC_ERROR                = "⚠️ Ошибка при обращении к Rocket.Chat. Попробуйте позже."
RC_NOT_FOUND            = "❌ Пользователь <code>{rc_login}</code> не найден в Rocket.Chat.\n\nПроверьте логин или зарегистрируйтесь на нашем сервере."  # {rc_login}
RC_INACTIVE             = "❌ Аккаунт <code>{rc_login}</code> в Rocket.Chat неактивен.\nОбратитесь к администратору сервера."  # {rc_login}
RC_OTP_MESSAGE          = "🔐 Ваш код подтверждения для входа в Telegram-бот Школы 21: *{code}*\n\nКод действителен 10 минут. Не передавайте его никому."  # {code}
OTP_SENT                = "📨 Код отправлен в личные сообщения Rocket.Chat (<code>{rc_login}</code>).\n\nВведите <b>6-значный код</b> из сообщения. У вас есть 3 попытки и 10 минут."  # {rc_login}
OTP_WRONG               = "❌ Неверный код. Осталось попыток: <b>{remaining}</b>."  # {remaining}
OTP_CONFIRMED           = "✅ Rocket.Chat аккаунт <code>{rc_login}</code> подтверждён!\n\n"  # {rc_login}
OTP_RESEND_BTN          = "🔁 Не пришёл код"
OTP_RATE_LIMITED        = (
    "🚨 <b>Превышен лимит запросов OTP-кода</b>\n\n"
    "👤 <b>Имя:</b> {tg_name}\n"
    "🆔 <b>Telegram ID:</b> <code>{tg_id}</code>\n"
    "🚀 <b>Rocket.Chat:</b> <code>{rc_login}</code>\n"
    "🔁 <b>Запросов кода:</b> {count} (лимит {limit})\n\n"
    "Заявка автоматически заморожена на 1 час."
)  # {tg_name}, {tg_id}, {rc_login}, {count}, {limit}

# ════════════════════════════════════════════════════════════════
# КОММЕНТАРИЙ И ПОДАЧА ЗАЯВКИ
# ════════════════════════════════════════════════════════════════

COMMENT_PROMPT          = (
    "💬 Напишите краткий комментарий к заявке (необязательно).\n\n"
    "Например: в каком городе учитесь, ваш поток, или просто «привет».\n\n"
    "Или нажмите кнопку ниже, чтобы пропустить."
)
COMMENT_SKIP_BTN        = "Пропустить"
APPLICATION_SUBMITTED   = "📨 Ваша заявка отправлена на рассмотрение!\nМы уведомим вас о решении в ближайшее время."

# ════════════════════════════════════════════════════════════════
# ОДОБРЕНИЕ / ОТКЛОНЕНИЕ
# ════════════════════════════════════════════════════════════════

INVITE_MESSAGE_TEMPLATE = (
    "🎉 Заявка одобрена!\n"
    "Ваша персональная ссылка для вступления:\n"
    "{invite_link}\n"
    "⚠️ Ссылка одноразовая и действует 24 часа.\n"
    "➖➖➖➖➖➖➖➖➖➖➖➖\n"
    "Перед переходом обязательно прочитай выжимку правил 👇\n"
    "<a href=\"{rules_url}\">(полная версия)</a>\n"
    "✌️ Чат {community_name} ({community_city})\n"
    "Наш закрытый комьюнити-чат для пиров и выпускников. Обсуждаем проекты, карьеру, помогаем с кодом и делимся опытом.\n"
    "📜 4 главных правила:\n"
    "😺 1. Будьте котиками. Никакой токсичности и перехода на личности. Спорить можно, ругаться — нельзя. Обсуждаем идеи, а не людей.\n"
    "🤫 2. Safe space. Что было в чате, остается в чате. Строго запрещено делать скриншоты переписок, форвардить сообщения из закрытых веток и деанонить участников.\n"
    "🛑 3. Без спама. Реклама услуг, вакансии и поиск команд — только в профильные ветки.\n"
    "🚫 4. Без читинга. Помогать (peer-to-peer) — круто. Скидывать готовое — запрещено. Нельзя кидать готовые решения заданий и закрытые материалы школы. Принцип: даем удочку, а не рыбу.\n"
    "➖➖➖➖➖➖➖➖➖➖➖➖\n"
    "⚖️ Модерация и баны:\n"
    "За мелкие нарушения (флуд, токсичность) мы выдаем предупреждения (Варны), которые перерастают в Мут, а затем в Бан.\n"
    "⛔️ Моментальный БАН (без предупреждений) выдается за: Скам, угрозы, жесткий читинг (слив ответов) и слив переписок из чата представителям администрации (АДМ) или участникам бассейна.\n"
    "➖➖➖➖➖➖➖➖➖➖➖➖\n"
    "Добро пожаловать! Нажимай на ссылку в начале сообщения и залетай в чат 🚀"
)  # {invite_link}, {rules_url}, {community_name}, {community_city}

APPROVED_USEFUL_COMMANDS = (
    "💡 <b>Полезные команды бота:</b>\n\n"
    "/profile — ваш профиль на платформе\n"
    "/where логин — найти участника в кампусе\n"
    "/invite &lt;КОД&gt; — применить инвайт-код\n"
    "/start — главное меню"
)

REJECTED_BASE           = "😔 Ваша заявка была отклонена."
REJECTED_REASON         = "\n\n<b>Причина:</b> {reason}"          # {reason}
REJECTED_COOLDOWN       = "\n\n🕐 Повторная заявка будет доступна через <b>{label}</b>."  # {label}
REJECTED_CAN_RETRY      = "\n\nВы можете подать заявку повторно командой /start."
REJECTED_SUPPORT        = "\n\n📞 По вопросам: {contacts}"         # {contacts}

# ════════════════════════════════════════════════════════════════
# ПРЕДУПРЕЖДЕНИЕ О НЕУДАЧНОЙ АВТОРИЗАЦИИ (алерт в чат модераторов)
# ════════════════════════════════════════════════════════════════

FAILED_AUTH_ALERT = (
    "⚠️ <b>Неуспешная попытка авторизации:</b> {reason}\n\n"
    "👤 <b>Имя:</b> {tg_name}\n"
    "🆔 <b>ID:</b> <code>{tg_id}</code>\n"
    "🔑 <b>Логин:</b> <code>{login}</code>"
)  # {reason}, {tg_name}, {tg_id}, {login}

# ════════════════════════════════════════════════════════════════
# ИНВАЙТ-КОДЫ
# ════════════════════════════════════════════════════════════════

INVITE_ACCEPTED_START   = "👋 Привет! Инвайт <b>{code}</b> от <b>{creator}</b> принят!\n\nДавайте начнём оформление заявки."  # {code}, {creator}
INVITE_INVALID          = "❌ Недействительный код."
INVITE_NO_APP_STORED    = "✅ Код <b>{code}</b> принят и будет применён к вашей заявке."  # {code}
INVITE_ATTACHED_OK      = "🎟 Инвайт-код <b>{code}</b> принят.\nК вашей заявке #{app_id} начислен <b>+1 trust</b>."  # {code}, {app_id}
INVITE_ALREADY_ATTACHED = "ℹ️ К заявке #{app_id} уже привязан инвайт-код."  # {app_id}
INVITE_ATTACH_FAILED    = "❌ Не удалось применить код — он недействителен или истёк."
INVITE_USAGE            = "Использование: <code>/invite КОД</code>\nНапример: <code>/invite A3F7C21B</code>"
INVITE_GENCODE_CAPTION  = "🎟 <b>Инвайт создан</b>\n\nСсылка: {link}\n\n<i>Одноразовый, действует 10 минут.</i>"  # {link}
INVITE_GENCODE_ERROR    = "🚨 Ошибка генерации кода: <code>{error}</code>"  # {error}
INVITE_NO_CODES         = "📭 У вас нет созданных инвайтов."
INVITE_CODES_HEADER     = "🎟 <b>Ваши инвайты</b>\n"
INVITE_CODE_ROW         = "{status} <code>{code}</code> | {used_by} | до {expires}"  # {status}, {code}, {used_by}, {expires}

# ════════════════════════════════════════════════════════════════
# ВЕРИФИКАЦИЯ (social trust)
# ════════════════════════════════════════════════════════════════

VERIFY_VOTE_CONFIRM     = "✅ Спасибо! Вы подтвердили участника."
VERIFY_VOTE_DECLINE     = "👍 Понял, спасибо за ответ."
VERIFY_VOTE_SUSPICIOUS  = "⚠️ Принято. Модераторы будут уведомлены."
VERIFY_VOTE_LABEL_SUFFIX= "\n\n<b>Ваш ответ:</b> {label}"  # {label}
VERIFY_ALREADY_VOTED    = "Вы уже ответили: {label}"       # {label}
VERIFY_NOT_VERIFIER     = "Вы не являетесь верификатором этой заявки."
VERIFY_VOTING_CLOSED    = "Голосование по этой заявке уже завершено."
VERIFY_BAD_REQUEST      = "Некорректный запрос."
VERIFY_UNKNOWN_VOTE     = "Неизвестный вариант ответа."
VERIFY_BAD_ID           = "Некорректный ID заявки."

# ════════════════════════════════════════════════════════════════
# МОДЕРАЦИЯ (кнопки и ответы)
# ════════════════════════════════════════════════════════════════

MOD_APP_NOT_FOUND       = "Заявка не найдена."
MOD_APP_ALREADY_DECIDED = "Заявка уже рассмотрена."
MOD_APPROVE_ERROR       = "🚨 Ошибка создания ссылки!"
MOD_APPROVED_ANSWER     = "✅ Одобрено. Пользователь уведомлён."
MOD_REJECTED_ANSWER     = "❌ Заявка отклонена, кулдаун: {label}."  # {label}
MOD_NOOP                = "Это решение уже принято."
MOD_ERROR_ALERT         = "🚨 <b>Ошибка:</b> {text}"  # {text}

REJECT_REASON_PROMPT    = "✏️ <b>Причина отклонения заявки #{app_id}</b>\n\nВыберите вариант <b>или напишите причину</b> следующим сообщением:"  # {app_id}
REJECT_COOLDOWN_PROMPT  = "⏱ Кулдаун на повторную заявку?\n<i>{label}</i>"  # {label}
REJECT_REASON_PREFIX    = "Причина: {reason}"  # {reason}
REJECT_NO_REASON        = "Без причины"

# ════════════════════════════════════════════════════════════════
# ПРОФИЛЬ (/profile и кнопка кабинета)
# ════════════════════════════════════════════════════════════════

PROFILE_ONLY_APPROVED   = "❌ Профиль доступен только одобренным участникам."
PROFILE_LOADING         = "🔄 Загружаю профиль…"
PROFILE_ERROR           = "⚠️ Не удалось загрузить профиль: {error}"  # {error}
PROFILE_HEADER          = "👤 <b>{login}</b>"                          # {login}
PROFILE_LINK            = "🔗 <a href='{url}'>Профиль на платформе</a>"  # {url}
PROFILE_LEVEL           = "⭐️ <b>Уровень:</b> {level}"                # {level}
PROFILE_XP              = "✨ <b>XP:</b> {exp} (+{exp_next} до следующего)"  # {exp}, {exp_next}
PROFILE_PARALLEL        = "📚 <b>Параллель:</b> {parallel}"            # {parallel}
PROFILE_COALITION       = "🏰 <b>Трайб:</b> {name}"                    # {name}
PROFILE_COALITION_RANK  = "🏰 <b>Трайб:</b> {name} (ранг {rank})"     # {name}, {rank}
PROFILE_PEER_PTS        = "🤝 <b>Поинты пир-ревью:</b> {pts}"         # {pts}
PROFILE_CODE_PTS        = "💻 <b>Поинты код-ревью:</b> {pts}"         # {pts}
PROFILE_COINS           = "🪙 <b>Монеты:</b> {coins}"                  # {coins}
PROFILE_PROJECTS_HEADER = "🚀 <b>Активные проекты:</b>"
PROFILE_SKILLS_HEADER   = "🛠 <b>Топ навыки:</b> {skills}"             # {skills}

# ════════════════════════════════════════════════════════════════
# КАРТОЧКА МОДЕРАТОРА (build_moderation_card)
# ════════════════════════════════════════════════════════════════

CARD_HEADER         = "📋 <b>Заявка #{app_id}</b>"                              # {app_id}
CARD_NAME           = "👤 <b>Имя:</b> {tg_name}"                                # {tg_name}
CARD_ID             = "🆔 <b>ID:</b> <code>{tg_id}</code>"                      # {tg_id}
CARD_LOGIN          = "🔑 <b>Логин:</b> <code>{login}</code>"                   # {login}
CARD_PROFILE_LINK   = "🔗 <b>Профиль:</b> <a href='{url}'>Профиль на платформе</a>"  # {url}
CARD_COALITION      = "⭐️ <b>Трайб:</b> {coalition}"                            # {coalition}
CARD_XP             = "✨ <b>XP:</b> {xp}"                                       # {xp}
CARD_BADGE_OK       = "🏅 <b>Бадж:</b> ✅ Welcome on board"
CARD_BADGE_FAIL     = "🏅 <b>Бадж:</b> ❌ Welcome on board не получен"
CARD_RC             = "🚀 <b>Rocket.Chat:</b> <code>{rc}</code>"                # {rc}
CARD_TEAMMATES      = "👥 <b>Тиммейты:</b> {logins}"                            # {logins}
CARD_COMMENT        = "💬 <b>Комментарий:</b> {comment}"                        # {comment}

# ════════════════════════════════════════════════════════════════
# КАБИНЕТ (кнопки approved-пользователя)
# ════════════════════════════════════════════════════════════════

CABINET_BTN_PROFILE = "👤 Профиль"
CABINET_BTN_GENCODE = "🎟 Создать инвайт"
CABINET_BTN_MYCODES = "📋 Мои инвайты"
CABINET_BTN_HELP   = "❓ Команды"
CABINET_NO_CODES    = "📭 У вас нет созданных инвайтов."
CABINET_CODES_HEADER = "🎟 <b>Ваши инвайты</b>\n"

# ════════════════════════════════════════════════════════════════
# /where
# ════════════════════════════════════════════════════════════════

WHERE_USAGE         = "Использование: <code>/where логин</code>\nНапример: <code>/where kylaknap</code>"
WHERE_IN_CAMPUS     = "🖥 <b>{login}</b> сейчас в кампусе\n📍 Место: <code>{seat}</code>"  # {login}, {seat}
WHERE_NOT_IN_CAMPUS = "🚶 <b>{login}</b> — не в кампусе."  # {login}
WHERE_ERROR         = "⚠️ Не удалось получить данные о местоположении."

# ════════════════════════════════════════════════════════════════
# НОВЫЙ УЧАСТНИК В ЧАТЕ (community.py)
# ════════════════════════════════════════════════════════════════

NEWCOMER_HEADER         = "👋 Новый участник!\n"
NEWCOMER_LOGIN          = "🔑 <b>Логин:</b> <code>{login}</code>"    # {login}
NEWCOMER_TG_ID          = "🆔 <b>ID:</b> <code>{tg_id}</code>"       # {tg_id}
NEWCOMER_TG_NAME        = "👤 <b>Имя:</b> {tg_name}"                 # {tg_name}
NEWCOMER_COALITION      = "⭐️ <b>Трайб:</b> {coalition}"             # {coalition}
NEWCOMER_PROFILE_LINK   = "🔗 <b>Профиль:</b> <a href='{url}'>Профиль на платформе</a>"  # {url}
NEWCOMER_WRONG_LINK     = (
    "🚨 <b>Вход по чужой ссылке — пользователь кикнут!</b>\n\n"
    "👤 <b>Нарушитель:</b> {tg_name}\n"
    "🆔 <b>ID:</b> <code>{tg_id}</code>\n\n"
    "🔗 <b>Ссылка принадлежит:</b> {owner_name}\n"
    "🆔 <b>ID владельца:</b> <code>{owner_id}</code>\n"
    "🔑 <b>Логин владельца:</b> <code>{owner_login}</code>"
)  # {tg_name}, {tg_id}, {owner_name}, {owner_id}, {owner_login}
NEWCOMER_UNVERIFIED_KICK = (
    "⚠️ <b>Неверифицированный пользователь кикнут!</b>\n\n"
    "👤 <b>Имя:</b> {tg_name}\n"
    "🆔 <b>ID:</b> <code>{tg_id}</code>\n"
    "🔗 <b>Ссылка:</b> <code>{invite_link}</code>"
)  # {tg_name}, {tg_id}, {invite_link}

# ════════════════════════════════════════════════════════════════
# РЕВЬЮ — уведомления в личку
# ════════════════════════════════════════════════════════════════

REVIEW_REMINDER_HOURS   = "📅 <b>Ревью через {hours} ч.!</b>"   # {hours}
REVIEW_REMINDER_HOUR    = "⏰ <b>Ревью через час!</b>"
REVIEW_REMINDER_MINUTES = "⏰ <b>Ревью через {minutes} мин.!</b>"  # {minutes}
REVIEW_PROJECT          = "📝 <b>Проект:</b> {title}"            # {title}
REVIEW_TIME             = "🕐 <b>Время:</b> {time}"              # {time}
REVIEW_CHECKER          = "👤 <b>Проверяющий:</b> <code>{login}</code>"  # {login}

# ════════════════════════════════════════════════════════════════
# ADMIN команды (admin.py)
# ════════════════════════════════════════════════════════════════

ADMIN_BAN_USAGE         = "❌ Формат: <code>/ban 123456789 [причина]</code>"
ADMIN_UNBAN_USAGE       = "❌ Формат: <code>/unban 123456789</code>"
ADMIN_DELUSER_USAGE     = "❌ Формат: <code>/deluser 123456789</code>"
ADMIN_USERINFO_USAGE    = "❌ Формат: <code>/userinfo 123456789</code>"
ADMIN_ID_NOT_INT        = "❌ TG ID должен быть числом."
ADMIN_USER_NOT_FOUND    = "❌ Пользователь <code>{tg_id}</code> не найден в базе."  # {tg_id}
ADMIN_ALREADY_BANNED    = "ℹ️ Пользователь <code>{tg_id}</code> уже заблокирован."  # {tg_id}
ADMIN_NOT_BANNED        = "ℹ️ Пользователь <code>{tg_id}</code> не заблокирован."   # {tg_id}
ADMIN_BANNED_OK         = "🚫 <code>{tg_id}</code> (<b>{tg_name}</b>) заблокирован.{reason}"  # {tg_id}, {tg_name}, {reason}
ADMIN_UNBANNED_OK       = "✅ <code>{tg_id}</code> (<b>{tg_name}</b>) разблокирован."  # {tg_id}, {tg_name}
ADMIN_DELUSER_CONFIRM   = "Удалить <code>{tg_id}</code> (<b>{tg_name}</b>) из БД? Это необратимо."  # {tg_id}, {tg_name}
ADMIN_DELUSER_OK        = "🗑 Пользователь <code>{tg_id}</code> удалён из БД."  # {tg_id}
ADMIN_DELUSER_CANCEL    = "❌ Удаление отменено."
ADMIN_CLEARDB_CANCEL    = "❌ Очистка отменена."
ADMIN_CLEARDB_OK        = "🗑 База данных очищена."
ADMIN_NO_EVENTS         = "📭 Ближайших мероприятий не найдено."
ADMIN_APPROVE_OK        = "✅ Заявка #{app_id} одобрена.\n👤 {tg_name} ({login}) уведомлён."  # {app_id}, {tg_name}, {login}
ADMIN_APPROVE_USAGE     = "Использование: <code>/approve &lt;app_id&gt;</code>"
ADMIN_BTN_CONFIRM_DEL   = "✅ Да, удалить"
ADMIN_BTN_CANCEL        = "❌ Отмена"
ADMIN_BTN_CLEARDB       = "💣 Да, очистить ВСЁ"
ADMIN_BTN_SKIP          = "Пропущено."

CABINET_HELP_TEXT = (
    "📖 <b>Команды для участников</b>\n\n"
    "/start — главное меню\n"
    "/profile — профиль на платформе\n"
    "/where <i>логин</i> — найти участника в кампусе\n"
    "/invite <i>код</i> — применить инвайт-код\n"
    "/вкампусе — кто сейчас в кампусе\n"
    "/алярм — ответом на сообщение, вызов модераторов"
)


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def tg_mention(tg_id: int, display: str) -> str:
    """Returns HTML link that mentions user by tg_id."""
    return f"<a href='tg://user?id={tg_id}'>{display}</a>"


# ════════════════════════════════════════════════════════════════
# ГОСТЕВЫЕ УЧАСТНИКИ
# ════════════════════════════════════════════════════════════════

GUEST_WELCOME = (
    "👋 Приветствуем гостя из другого кампуса!\n\n"
    "🔑 <b>Логин:</b> <code>{login}</code>\n"
    "🆔 <b>ID:</b> <code>{tg_id}</code>\n"
    "👤 <b>Имя:</b> {tg_name}\n"
    "🏠 <b>Кампус:</b> {campus}\n"
    "⭐️ <b>Трайб:</b> {coalition}\n"
    "🔗 <b>Профиль:</b> <a href='{url}'>Профиль на платформе</a>"
)  # {login}, {tg_id}, {tg_name}, {campus}, {coalition}, {url}

GUEST_INVITE_CREATED = (
    "✅ <b>Гостевой инвайт создан</b>\n\n"
    "👤 Для: <a href=\'tg://user?id={tg_id}\'>{tg_name}</a>\n"
    "🔑 Логин: <code>{login}</code>\n"
    "🏠 Кампус: {campus}\n\n"
    "🔗 Ссылка отправлена в личку гостю."
)

GUEST_INVITE_DM = (
    "👋 Привет! Тебя приглашают в чат Школы 21.\n\n"
    "Нажми на ссылку ниже чтобы вступить:\n"
    "{invite_link}\n\n"
    "⚠️ Ссылка одноразовая."
)


CABINET_GENCODE_ERROR = "❌ Ошибка генерации: <code>{error}</code>"
