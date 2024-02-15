import json
from typing import List, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import (
    JsonOutputParser,
    StrOutputParser
)
from langchain_core.prompts import (
    ChatPromptTemplate,
    PromptTemplate
)
from . import (
    GPT_MODEL_NAME,
    count_tokens_in_prompt_messages,
    count_tokens_in_string,
    _skip_curly_brackets,
)
from utils import prettify_str, logger

from langchain_core.pydantic_v1 import BaseModel, Field, Json

class CellUpdate(BaseModel):
    cell_id: str = Field(description="cell id")
    # line_number: int = Field(description="line number")
    # update_details: str = Field(description="update made to the cell")
    learned_lesson: str = Field(description="learned lesson from this update")
    teacher_question: str = Field(description="question that can be made by a teacher from the lesson")
    student_answer: str = Field(description="answer to the question from an excellent student point of view")

# SAMPLE_QUESTIONS = """
# COMPLETE_QUESTIONS = [
#     "Was that output expected?",
#     "What caused this error?",
#     "What are you doing right now?",
# ]

# FUNCTION_QUESTION_TEMPLATES = [
#     "What does the function {} do?",
#     "What other arguments could be passed to function {}?",
#     "What kind of problem did {} solve?",
#     "What are the next steps after running {} function?",
# ]

# FUNC_STR_QUESTION_TEMPLATES = [
#     "Are there other ways to perform {}?",
#     "What is the next step after {}?",
# ]

# VARIABLE_QUESTION_TEMPLATES = [
#     "What do you expect to be stored in variable {}",
# ]

# BASH_COMMAND_TEMPLATES = [
#     "What is the use of the {} bash command?"
# ]

# FLAG_QUESTION_TEMPLATES = [
#     "What is the {flag} flag used for in {command} bash command?"
# ]
# """

SAMPLE_QUESTIONS = """
- "Was that output expected?"
- "What caused this error?"
- "What are you doing right now?"
- "What does the function {} do?"
- "What other arguments could be passed to function {}?"
- "What kind of problem did {} solve?"
- "What are the next steps after running {} function?"
- "Are there other ways to perform {}?"
- "What is the next step after {}?"
- "What do you expect to be stored in variable {}"
- "What is the use of the {} bash command?"
- "What is the {flag} flag used for in {command} bash command?"
"""



PROMPT_TEMPLATE_HEADER = """
You will be provided with two states of Python Notebook Cells at two consecutive timesteps. Each state is followed by its structured rough explanation (Might contain errors). Given the differences between the states of the notebook cells, state the lesson learned from the modification done on State t to get to State t+1 between the notebook code (Why was it made?). Additionally add question, and its corresponding answer to the lesson stated. The lesson shall be written according to the following JSON Schema: {CELL_UPDATE_SCHEMA}

DO NOT at all make naive questions and answers, but make these questions from a teacher point of view about the lesson learned from the modification that cannot be answered by just stating what is in the block of code from a good student point of view. Examples of naive questions that are not allowed:
- "what is the output of the cell?"
- "what is the modification done?"
- "what is the correct code?"
- "what was done in the cell?"
- "what is the code doing?"
- "what is the code?"
- "why was the code modified?"

State t:
{notebook_state_t}

Explanation of State t:
{explanation_t}

State t+1:
{notebook_state_t_plus_1}

Explanation of State t+1:
{explanation_t_plus_1}

"""

def make_questions_prompt(
    nb_state_t, nb_state_t_plus_1,
    explanation_t, explanation_t_plus_1,
    prev_generated_questions: List[str]
):
    output_parser = StrOutputParser()

    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE_HEADER,
        input_variables=[
            'notebook_state_t', 'explanation_t',
            'notebook_state_t_plus_1', 'explanation_t_plus_1',
            # 'prev_generated_questions'
        ],
        partial_variables={
            # 'sample_questions': SAMPLE_QUESTIONS
            'CELL_UPDATE_SCHEMA': CellUpdate.schema_json(indent=2)
        }
    )

    prompt = prompt.partial(**{
        'notebook_state_t': str(nb_state_t),
        'explanation_t': json.dumps(explanation_t, indent=2),
        'notebook_state_t_plus_1': str(nb_state_t_plus_1),
        'explanation_t_plus_1': json.dumps(explanation_t_plus_1, indent=2),
        # 'prev_generated_questions': "\n".join([prev_response for prev_response in prev_generated_questions])
    })


    logger.trace(f'Generate Questions Prompt:\n{prettify_str(prompt)}')

    llm = ChatOpenAI(
        model=GPT_MODEL_NAME,
        # temperature=0,
        # model_kwargs={
        #     # "max_tokens": num_tokens*3,
        #     # "top_p": 1,
        #     "frequency_penalty": 0.5,
        #     "presence_penalty": 0.5,
        # }
    )


    chain = prompt | llm | output_parser

    response = chain.invoke({})
    num_tokens_from_response = count_tokens_in_string(response)
    print(f'num_tokens from response: {num_tokens_from_response}')

    return response
