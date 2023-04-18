import os
from time import sleep

from typing import List, Any

import openai
from langchain import PromptTemplate
from langchain.callbacks import CallbackManager
from langchain.chat_models import ChatOpenAI
from openai.error import RateLimitError
from langchain.schema import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

from src.constants import PRICING_GPT4_PROMPT, PRICING_GPT4_GENERATION, PRICING_GPT3_5_TURBO_PROMPT, \
    PRICING_GPT3_5_TURBO_GENERATION, CHARS_PER_TOKEN
from src.options.generate.templates_system import template_system_message_base, executor_example, docarray_example, client_example
from src.utils.string_tools import print_colored


class GPTSession:
    def __init__(self, task_description, test_description, model: str = 'gpt-4', ):
        self.task_description = task_description
        self.test_description = test_description
        self.configure_openai_api_key()
        if model == 'gpt-4' and self.is_gpt4_available():
            self.model_name = 'gpt-4'
            self.pricing_prompt = PRICING_GPT4_PROMPT
            self.pricing_generation = PRICING_GPT4_GENERATION
        else:
            if model == 'gpt-4':
                print_colored('GPT-4 is not available. Using GPT-3.5-turbo instead.', 'yellow')
                model = 'gpt-3.5-turbo'
            self.model_name = model
            self.pricing_prompt = PRICING_GPT3_5_TURBO_PROMPT
            self.pricing_generation = PRICING_GPT3_5_TURBO_GENERATION
        self.chars_prompt_so_far = 0
        self.chars_generation_so_far = 0

    @staticmethod
    def configure_openai_api_key():
        if 'OPENAI_API_KEY' not in os.environ:
            raise Exception('''
You need to set OPENAI_API_KEY in your environment.
If you have updated it already, please restart your terminal.
'''
)
        openai.api_key = os.environ['OPENAI_API_KEY']

    @staticmethod
    def is_gpt4_available():
        try:
            for i in range(5):
                try:
                    openai.ChatCompletion.create(
                        model="gpt-4",
                        messages=[{
                            "role": 'system',
                            "content": 'you respond nothing'
                        }]
                    )
                    break
                except RateLimitError:
                    sleep(1)
                    continue
            return True
        except openai.error.InvalidRequestError:
            return False

    def cost_callback(self, chars_prompt, chars_generation):
        self.chars_prompt_so_far += chars_prompt
        self.chars_generation_so_far += chars_generation
        print('\n')
        money_prompt = self.calculate_money_spent(self.chars_prompt_so_far, self.pricing_prompt)
        money_generation = self.calculate_money_spent(self.chars_generation_so_far, self.pricing_generation)
        print('Total money spent so far on openai.com:', f'${money_prompt + money_generation:.3f}')
        print('\n')

    def calculate_money_spent(self, num_chars, price):
        return round(num_chars / CHARS_PER_TOKEN * price / 1000, 3)

    def get_conversation(self, system_definition_examples: List[str] = ['executor', 'docarray', 'client']):
        return _GPTConversation(self.model_name, self.cost_callback, self.task_description, self.test_description, system_definition_examples)


class AssistantStreamingStdOutCallbackHandler(StreamingStdOutCallbackHandler):
    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token. Only available when streaming is enabled."""
        print_colored('', token, 'green', end='')


class _GPTConversation:
    def __init__(self, model: str, cost_callback, task_description, test_description, system_definition_examples: List[str] = ['executor', 'docarray', 'client']):
        self._chat = ChatOpenAI(
            model_name=model,
            streaming=True,
            callback_manager=CallbackManager([AssistantStreamingStdOutCallbackHandler()]),
            verbose=os.environ['VERBOSE'].lower() == 'true',
            temperature=0,
        )
        self.cost_callback = cost_callback
        self.messages: List[BaseMessage] = []
        self.system_message = self._create_system_message(task_description, test_description, system_definition_examples)
        if os.environ['VERBOSE'].lower() == 'true':
            print_colored('system', self.system_message.content, 'magenta')

    def chat(self, prompt: str):
        chat_message = HumanMessage(content=prompt)
        self.messages.append(chat_message)
        if os.environ['VERBOSE'].lower() == 'true':
            print_colored('user', prompt, 'blue')
            print_colored('assistant', '', 'green', end='')
        messages = [self.system_message] + self.messages
        response = self._chat(messages)
        if os.environ['VERBOSE'].lower() == 'true':
            print()
        self.cost_callback(sum([len(m.content) for m in messages]), len(response.content))
        self.messages.append(response)
        return response.content

    @staticmethod
    def _create_system_message(task_description, test_description, system_definition_examples: List[str] = []) -> SystemMessage:
        system_message = PromptTemplate.from_template(template_system_message_base).format(
            task_description=task_description,
            test_description=test_description,
        )
        if 'executor' in system_definition_examples:
            system_message += f'\n{executor_example}'
        if 'docarray' in system_definition_examples:
            system_message += f'\n{docarray_example}'
        if 'client' in system_definition_examples:
            system_message += f'\n{client_example}'
        return SystemMessage(content=system_message)
