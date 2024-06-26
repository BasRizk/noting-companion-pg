import json
from typing import List, Tuple
from langchain_openai import ChatOpenAI, OpenAI
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
from langchain_core.runnables import RunnableLambda, RunnableParallel


# class CellUpdate(BaseModel):
#     cell_id: str = Field(description="cell id")
#     # line_number: int = Field(description="line number")
#     # update_details: str = Field(description="update made to the cell")
#     learned_lesson: str = Field(description="learned lesson from this update")
#     teacher_question: str = Field(description="question that can be made by a teacher from the lesson")
#     student_answer: str = Field(description="answer to the question from an excellent student point of view")

# SAMPLE_QUESTIONS = """
# - "Was that output expected?"
# - "What caused this error?"
# - "What are you doing right now?"
# - "What does the function {} do?"
# - "What other arguments could be passed to function {}?"
# - "What kind of problem did {} solve?"
# - "What are the next steps after running {} function?"
# - "Are there other ways to perform {}?"
# - "What is the next step after {}?"
# - "What do you expect to be stored in variable {}"
# - "What is the use of the {} bash command?"
# - "What is the {flag} flag used for in {command} bash command?"
# """


GENERATE_QUESTIONS_TEMPLATE_HEADER = """
You are queried with a state of cells of Python Notebook at time t1 and the change applied to these cells to get to a different state at time t2. Your task is to generate questions corresponding to the changes with respect to the overall prospectives of what is needed to be implemented or fixed if any, and overview of what has been completed, and/or why?


A student will answer these question, the student has access to the whole notebook staFtes including their source code and the change that occured. Make non-trivial specific questions to ask the student on the change. Act a a teacher, and write questions in a numbered bullet points format as follows:
```
1. questions statement
2. questions statement
..
```

Avoid questions asking to student to recall code or changes. Remove also questions that are already answered answered by later question or looking at the code. Do not make questions such as the following:
- "What specific change was made to the code.."
- "What changes were made..."
- "what is the output of the cell.."
- "what is the modification done.."
- "what is the correct code.."
- "what was done in the cell.."
- "what is the code doing.."
- "why was the code modified.."
- or any other questions that give the same meaning.
The above questions are not allowed, and will be filtered out!


Query:
Notebook State @ t1:
{nb_state_t_minus_1}

Changes to get to Notebook State @ t2:
{nb_updates}

Questions:
"""




REVIEW_QUESTIONS_TEMPLATE_HEADER = """
You are queried with a state of cells of Python Notebook at time t1 and the change applied to these cells to get to a different state at time t2, and the questions generated by a teacher on these changes. Your task is to reduce, review and filter this previous list of questions, remove any bad questions, any redundancies, and add any good questions that you think are missing. We want to have the final list consisting of at most {max_number_questions} questions. Make sure to rewrite the questions in the same format.

A student will answer these question, the student has access to the whole notebook states including their source code and the change that occured. Make non-trivial specific questions to ask the student on the change. Act a a teacher, and write questions in a numbered bullet points format. Avoid questions asking to recall code or changes. Avoid questions asking to student to recall code or changes. Remove also questions that are already answered answered by later question or looking at the code.

Filter out any question that looks like the following:
- "What specific change was made to the code.."
- "What changes were made..."
- "what is the output of the cell.."
- "what is the modification done.."
- "what is the correct code.."
- "what was done in the cell.."
- "what is the code doing.."
- "why was the code modified.."
- or any other questions that give the same meaning.


Query:
Notebook State @ t1:
{nb_state_t_minus_1}

Changes to get to Notebook State @ t2:
{nb_updates}

Previous list of Questions:
{prev_questions}

Updated list of Questions:
"""

from parsers.nb_parser import NotebookParser

def make_questions_prompt(
    nb_state_t_minus_1: NotebookParser,
    nb_state_t: NotebookParser,
    max_num_questions_per_update = 3,
    # change_explanation: str,
):
    output_parser = StrOutputParser()

    prompt = PromptTemplate(
        template=GENERATE_QUESTIONS_TEMPLATE_HEADER,
        input_variables=[
            'nb_state_t_minus_1', 'nb_updates'
        ]
    )
    nb_updates = nb_state_t_minus_1.get_updates(nb_state_t)
    nb_updates = [cell.get_json() for cell in nb_updates]

    generate_prompt = prompt.partial(**{
        'nb_state_t_minus_1': nb_state_t_minus_1.get_cells(),
        'nb_updates': nb_updates
    })

    logger.trace(f'Generate Questions Prompt:\n{prettify_str(prompt)}')

    llm = ChatOpenAI(
        model=GPT_MODEL_NAME,
        temperature=0.9
    )

    # llm = OpenAI(
    #     model='gpt-3.5-turbo-instruct',
    #     temperature=0.7
    # )

    def parse(response):
        import re
        try:
            questions = [
                re.sub(r'\d+.', '', question, 1).strip()
                for question in response.split('\n')
            ]
            return [question for question in questions if question]
        except:
            raise Exception(f'Error, response is not a valid format:\n{response.content}')
    questions_parser = RunnableLambda(lambda x: parse(x))


    generate_chain = generate_prompt | llm | output_parser
    generated_questions = generate_chain.invoke({})

    review_prompt = PromptTemplate(
        template=REVIEW_QUESTIONS_TEMPLATE_HEADER,
        input_variables=[
            'nb_state_t_minus_1', 'nb_updates', 'prev_questions'
        ]
    )
    review_chain = review_prompt | llm | output_parser | questions_parser
    reviewed_questions = review_chain.invoke({
        'max_number_questions': max_num_questions_per_update*len(nb_updates),
        'prev_questions': generated_questions,
        'nb_state_t_minus_1': nb_state_t_minus_1.get_cells(),
        'nb_updates': nb_updates
    })


    return reviewed_questions