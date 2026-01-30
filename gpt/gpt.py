from typing import Optional, List, Dict, Tuple
import logging

class GPT:
    def __init__(self, openai, question_about_plan_prompt: str):
        self.openai = openai
        self.question_about_plan_prompt = question_about_plan_prompt


    def chat_for_plan(self, prompt: str) -> str:
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.7
            )
            reply = response.choices[0].message.content
            return self._extract_clean_json(reply)

        except Exception as e:
            logging.error(f"Ошибка GPT {e}")
            return ''
        
    def _extract_clean_json(self, text: str) -> str:
        brace_stack = []
        start_index = None

        for i, char in enumerate(text):
            if char == '{':
                if start_index is None:
                    start_index = i
                brace_stack.append('{')
            elif char == '}':
                if brace_stack:
                    brace_stack.pop()
                    if not brace_stack:
                        json = text[start_index:i + 1]
                        return json

        raise ValueError("Не удалось извлечь валидный JSON из текста.")
        
    def ask_question_gpt(self, question_dialog: Optional[List[Dict]], user_input: Optional[str], plan_part: Optional[str]) -> Tuple:
        if plan_part:
            question_dialog = [{"role": "system", "content": self.question_about_plan_prompt + f"\n{plan_part}"}]
            question_dialog.append({"role": "user", "content": "Привет, у меня есть вопросы по предоставленному тобой плану."})
            try:
                response = self.openai.chat.completions.create(
                    model="gpt-4o",
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
                model="gpt-4o",
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
        
    def create_reminder(self, prompt: str) -> str:
        try:
            message = [{"role": "system", "content": prompt}]
            response = self.openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=message,
                        temperature=0.7
                    )
            reply = response.choices[0].message.content
            return reply
        except Exception as e:
            logging.error(f"Ошибка в gpt\\create_reminder {e}")
            return ''
        