from langchain_openai import ChatOpenAI, OpenAI
from langchain_core.output_parsers import (
    JsonOutputParser,
    StrOutputParser
)
from langchain_core.output_parsers.json import (
    parse_partial_json
)
from langchain_core.prompts import (
    ChatPromptTemplate,
    PromptTemplate
)
from .. import (
    GPT_MODEL_NAME,
    count_tokens_in_prompt_messages,
    count_tokens_in_string,
    _skip_curly_brackets,
)

from langchain_core.runnables import RunnableLambda, RunnableParallel

from utils import prettify_str, logger

from parsers.nb_parser import NotebookParser
from typing import List, Tuple
from langchain_core.pydantic_v1 import BaseModel, Field, Json


class CellExplanation(BaseModel):
    cell_type: str = Field(description="insert markdown or code")
    cell_id: str = Field(description="cell id")
    cell_explanation: str = Field(description="explanation of the cell")
    relations_to_other_cells: list = Field(description="list of cell ids that this cell is related to")
    relations_details: list = Field(description="list of details of the relations")
    # implemented: bool = Field(description="whether the cell has been implemented")
    # what_to_be_implemented: str = Field(description="what to be implemented if not implemented")

class NotebookSummary(BaseModel):
    summary: str = Field(description="summary of the notebook")
    key_cells: list = Field(description="list of ids of most critical cells")
    relations: list = Field(description="list of relations between key_cells")
    implemented: bool = Field(description="whether the notebook has been implemented")
    what_to_be_implemented: list = Field(description="list of cells that need to be implemented or modified")

class NotebookExplanation(BaseModel):
    cells: Json[List[CellExplanation]] = Field(description="list of cells explanations")
    summary: NotebookSummary = Field(description="summary of the notebook")

NB_CELLS_EXPLANATION_TEMPLATE = """
[
    {
        "cell_type": "insert markdown or code",
        "cell_id": "cell id",
        "cell_explanation": "insert first cell explanation here",
        "relations_ids": list of closely connected cells ids,
        "relations": list of explanations of the relations,
    },

    ...

    {
        "cell_type": "insert markdown or code",
        "cell_id": "insert cell id",
        "cell_explanation": "insert last cell explanation here",
        "relations_ids": list of closely connected cells ids,
        "relations": list of explanations of the relations
    },
    {
        "summary": "insert a summary of the notebook",
        "key_cells": list of ids of most critical cells,
        "relations_ids": list of closely connected cells ids,
        "relations": list of explanations of the relations,
        "implemented": True if this notebook task is complete, False otherwise,
        "cells_to_be_implemented": list of cells that need to be implemented or modified
    }
]
"""
# PROMPT_TEMPLATE_HEADER = """
# You will be provided with Python notebook cells. Your task is to explain what is needed to be implemented or modified if any implementation is not complete or not proper yet.

# Ensure that each cell is explained independently while mentioning all relevant context needed to explain them in detail (Example of context is attachment and connection to previous cells), then give an overall summary of the whole notebook at the end.

# {format_instructions}
# {notebook_state}

# """

PROMPT_TEMPLATE_HEADER = """
You will be queried with a particular state of Python Notebook cells at time t. Your task is to contruct a clarification documentation per each cells considering what is needed to be implemented if any implementation is not complete or not proper yet, and what has been completed, and why?

Ensure that each cell is explained independently while mentioning all relevant context needed to explain them in detail (Example of context is attachment and connection to previous cells), then give an overall summary of the whole notebook at the end. Provide output in JSON format as follows:

{NB_EXPLANATION_FORMAT}

Query:
{notebook_state}

"""


VERIFY_PROMPT_TEMPLATE_HEADER = """
You will be queried with a particular state of Python Notebook cells at time t, as well as the explanation of the cells. Your task is to verify the correctness of the explanation of each cell and the overall summary of the whole notebook. Rewrite the explanation with any adjustments you see fit in the same JSON format as follows:

{NB_EXPLANATION_FORMAT}

Query:
Notebook State:
{notebook_state}

Explanation:
{state_explanation}

"""





def code_explain_prompt(nb_state_cells: NotebookParser, prev_messages=[]):
    # TODO previous messages are not being used here
    assert prev_messages is None or len(prev_messages) == 0, 'Previous messages are not implemented yet'
    if prev_messages and prev_messages[0].get('role') != 'system':
        raise Exception('First message must be system message')

    # output_parser = JsonOutputParser(pydantic_object=NotebookExplanation)
    # output_parser = JsonOutputParser()

    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE_HEADER,
        input_variables=['notebook_state'],
        partial_variables={
            'NB_EXPLANATION_FORMAT': NB_CELLS_EXPLANATION_TEMPLATE,
        #     'format_instructions': output_parser.get_format_instructions(),
        }
    )

    verify_prompt = PromptTemplate(
        template=VERIFY_PROMPT_TEMPLATE_HEADER,
        input_variables=['state_explanation', 'notebook_state'],
        partial_variables={
            'NB_EXPLANATION_FORMAT': NB_CELLS_EXPLANATION_TEMPLATE,
        }
    )

    logger.trace(f'Code Explain Prompt:\n{prettify_str(prompt)}')
    llm = ChatOpenAI(
        model=GPT_MODEL_NAME,
        temperature=0.7,
        # model_kwargs={
        #     # "max_tokens": num_tokens*3,
        #     # "top_p": 1,
        #     "frequency_penalty": 0.5,
        #     "presence_penalty": 0.5,
        # }
    )



    def parse(response):
        try:
            response = eval(response.content)
        except:
            try:
                response = parse_partial_json(response.content)
            except:
                raise Exception(f'Error, response is not a valid json:\n{response.content}')

        response = {
            "cells": response[:-1],
            "summary": response[-1]
        }
        if isinstance(nb_state_cells, list):
            if len(response['cells']) != len(nb_state_cells):
                raise Exception(f'Error, response cells count({len(response["cells"])}) != nb_state_cells count({len(nb_state_cells)})')

        return response

    exp_parser = RunnableLambda(lambda x: parse(x))
    chain = prompt | llm | exp_parser
    state_explanation = chain.invoke({
        'notebook_state': str(nb_state_cells)
    })

    chain = verify_prompt | llm | exp_parser
    verified_explanation = chain.invoke({
        'state_explanation': str(state_explanation),
        'notebook_state': str(nb_state_cells)
    })

    if state_explanation != verified_explanation:
        logger.warning(f'Explanation verification failed, returning verified explanation')
        logger.trace(f'State Explanation:\n{state_explanation}')
        logger.trace(f'Verified Explanation:\n{verified_explanation}')
        breakpoint()

    num_tokens_from_response = count_tokens_in_string(verified_explanation)
    logger.trace(f'num_tokens from response: {num_tokens_from_response}')

    return verified_explanation