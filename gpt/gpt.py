from typing import Optional, List, Dict, Tuple, Type
import logging

class GPT:
    def __init__(self, openai, question_about_plan_prompt: str):
        self.openai = openai
        self.question_about_plan_prompt = question_about_plan_prompt


    async def chat_for_plan(self, prompt: str) -> str:
        logging.info(f"Внутри класса GPT: prompt - {prompt}")

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.7
            )
            reply = response.choices[0].message.content
            
            return reply

        except Exception as e:
            logging.error(f"Ошибка GPT {e}")
            return (None, f"Ошибка {e}", 2)
        
    async def ask_question_gpt(self, question_dialog: Optional[List[Dict]], user_input: Optional[str], plan_part: Optional[str]) -> Tuple:
        if plan_part:
            question_dialog = [{"role": "system", "content": self.question_about_plan_prompt + f"\n{plan_part}"}]
            question_dialog.append({"role": "user", "content": "Привет, у меня есть вопросы по предоставленному тобой плану."})
            try:
                response = self.openai.chat.completions.create(
                    model="gpt-3.5-turbo",
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
                model="gpt-3.5-turbo",
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
        