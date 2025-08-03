from typing import Optional, List, Dict, Tuple, Type
import logging

class GPT:
    def __init__(self, openai, promt: str):
        self.openai = openai
        self.system_promt = promt


    async def chat_for_plan(self, dialog: Optional[List[Dict]], user_input: str) -> Tuple: # возвращается (диалог, ответ, статус-код)
        logging.info(f"Внутри класса: dialog - {dialog}")
        if dialog is None:
            dialog = [{"role": "system", "content": self.system_promt}]
            print("DIALOG IS NONE")
        dialog.append({"role": "user", "content": user_input})

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=dialog,
                temperature=0.7
            )
            reply = response.choices[0].message.content
            logging.info(f"REPLY ОТ ГПТ {reply}")
            if "я не понял тебя" in reply.lower():
                dialog.pop()
                return (dialog, reply, 1)
            elif "очень жаль" in reply.lower():
                return (None, reply, 2)
            else:
                dialog.append({"role": "assistant", "content": reply})
                return (dialog, reply, 0)


        except Exception as e:
            logging.error(f"Ошибка GPT {e}")
            return (None, f"Ошибка {e}", 2)