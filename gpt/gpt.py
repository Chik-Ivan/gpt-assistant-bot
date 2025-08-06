from typing import Optional, List, Dict, Tuple, Type
import logging

class GPT:
    def __init__(self, openai, system_promt: str, question_promt: str):
        self.openai = openai
        self.system_promt = system_promt
        self.question_promt = question_promt


    async def chat_for_plan(self, dialog: Optional[List[Dict]], user_input: str) -> Tuple: # возвращается (диалог, ответ, статус-код)
        logging.info(f"Внутри класса: dialog - {dialog}")
        if not dialog:
            dialog = [{"role": "system", "content": self.system_promt}]
        dialog.append({"role": "user", "content": user_input})

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=dialog,
                temperature=0.7
            )
            reply = response.choices[0].message.content
            
            if "очень жаль" in reply.lower():
                logging.info("ОЧЕНЬ ЖАЛЬ")
                return (None, reply, 2)
            elif "я не понял тебя" in reply.lower() or "давай уточним" in reply.lower():
                dialog.append({"role": "assistant", "content": reply})
                return (dialog, reply, 1)
            else:
                dialog.append({"role": "assistant", "content": reply})
                return (dialog, reply, 0)


        except Exception as e:
            logging.error(f"Ошибка GPT {e}")
            return (None, f"Ошибка {e}", 2)
        
    def ask_question_gpt(self, question_dialog: Optional[List[Dict]], user_input: Optional[str], plan_part: Optional[str]) -> Tuple:
        if plan_part:
            question_dialog = [{"role": "system", "content": self.system_promt + f"\n{plan_part}"}]
            question_dialog.append({"role": "user", "content": "Привет, у меня есть вопросы по предоставленному тобой плану."})
            try:
                response = self.openai.chat.completions.create(
                    model="gpt-3.5",
                    messages=question_dialog,
                    temperature=0.7
                )
                reply = response.choices[0].message.content
                question_dialog.append({"role": "assistant", "content": reply})
                return question_dialog, reply, 0
            except Exception as e:
                logging.error(f"Ошибка GPT {e}")
                return (None, f"Ошибка {e}", 2)
        try:
            question_dialog.append({"role": "user", "content": user_input if user_input else ""})
            response = self.openai.chat.completions.create(
                model="gpt-3.5",
                messages=question_dialog,
                temperature=0.7
            )
            reply = response.choices[0].message.content
            
            if "что смог помочь тебе" in reply.lower():
                return (question_dialog, reply, 1)
            else:
                question_dialog.append({"role": "assistant", "content": reply})
                return (question_dialog, reply, 0)


        except Exception as e:
            logging.error(f"Ошибка GPT {e}")
            return (None, f"Ошибка {e}", 2)
        