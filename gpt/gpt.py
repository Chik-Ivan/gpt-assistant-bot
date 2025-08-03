from typing import Optional, List, Dict, Tuple, Type


class GPT:
    def __init__(self, openai, promt: str):
        self.openai = openai
        self.system_promt = promt


    async def chat_for_plan(self, dialog: Optional[List[Dict]], user_input: str) -> Tuple: # возвращается (диалог, ответ, статус-код)
        if dialog is None:
            dialog = [{"role": "system", "content": self.system_prompt}]
        dialog.append({"role": "user", "content": user_input})

        try:
            response = self.openai.ChatCompletion.create(
                model="gpt-4o",
                messages=dialog,
                temperature=0.7
            )
            reply = response["choices"][0]["message"]["content"]

            if "я не понял тебя" in reply.lower():
                dialog.pop()
                return (dialog, reply, 1)
            if "очень жаль" in reply.lower():
                return (None, reply, 2)
            else:
                dialog.append({"role": "assistant", "content": reply})
                return (dialog, reply, 0)


        except Exception as e:
            return f"Ошибка GPT: {e}"