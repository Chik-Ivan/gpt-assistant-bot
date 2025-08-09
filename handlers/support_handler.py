from aiogram import Router, F
from handlers.current_plan_handler import check_plan
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from keyboards.all_inline_keyboards import support_kb


support_router = Router()


@support_router.message(F.text=="🆘 поддержка")
async def support(message: Message, state: FSMContext):
    user = await check_plan(message.from_user.id, message, state)
    if not user:
            return
    text = ("Кнопка ниже перенесет вас в чат с поддержкой, где вы сможете задать свой вопрос.\n"
            "Большую часть проблем, обычно, можно решить просто <b>перезапустив бота</b>, если после этого ваша проблема не решена, то воспользуйтесь кнопкой\n"
            "Не стоит злоупотреблять этой возможностью, спамить или оскорблять операторов.\n"
            "Пишите четко и по существу, не разделяя свое сообщение на множество более мелких.\n"
            "Спасибо за понимание!")
    await message.answer(text, reply_markup=support_kb()) 
