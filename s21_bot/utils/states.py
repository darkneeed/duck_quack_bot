from aiogram.fsm.state import State, StatesGroup


class ApplicationFSM(StatesGroup):
    waiting_login = State()

    waiting_rocket_login = State()

    waiting_otp = State()

    waiting_comment = State()


class ProfileCardFSM(StatesGroup):
    waiting_photo = State()

    waiting_comment = State()

    waiting_max_link = State()
