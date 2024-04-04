import json
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
from . import (
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


# class CellExplanation(BaseModel):
#     cell_type: str = Field(description="insert markdown or code")
#     cell_id: str = Field(description="cell id")
#     cell_explanation: str = Field(description="explanation of the cell")
#     relations_to_other_cells: list = Field(description="list of cell ids that this cell is related to")
#     relations_details: list = Field(description="list of details of the relations")
#     # implemented: bool = Field(description="whether the cell has been implemented")
#     # what_to_be_implemented: str = Field(description="what to be implemented if not implemented")

# class NotebookSummary(BaseModel):
#     summary: str = Field(description="summary of the notebook")
#     key_cells: list = Field(description="list of ids of most critical cells")
#     relations: list = Field(description="list of relations between key_cells")
#     implemented: bool = Field(description="whether the notebook has been implemented")
#     what_to_be_implemented: list = Field(description="list of cells that need to be implemented or modified")

# class NotebookExplanation(BaseModel):
#     cells: Json[List[CellExplanation]] = Field(description="list of cells explanations")
#     summary: NotebookSummary = Field(description="summary of the notebook")

NB_CELLS_EXPLANATION_TEMPLATE = """
[
    {
        "cell_type": choose "markdown" or code",
        "cell_id": <insert cell_id>,
        "explanation": <insert sentences of detailed explanation of the update here>,
        "relations_ids": list closely connected cells ids (format:[<cell_id>, <cell_id>, ...]) if any,
        "relations": list explanations of these relations in the same order as relations_ids if any,
    }
]
"""


PROMPT_TEMPLATE_HEADER = """
You will be queried with a state of Python Notebook cells at time t1 and the change applied to the cells at to get the state at time t2. Your task is to explain each change with respect to the overall prospectives of what is needed to be implemented or fixed if any, and overview of what has been completed, and why?

Ensure that each change is explained while mentioning all relevant context needed to explain them in detail (Example of context is attachment and connection to previous cells). Do not rewrite the code, but explain the changes in the code in the following JSON format:

{NB_EXPLANATION_FORMAT}

Query:
Notebook State @ t1:
{nb_state_t_minus_1}

Updates to get to Notebook State @ t2:
{nb_updates}

Explanation:
"""


def get_diff_nb_states(
    nb_state_1: NotebookParser,
    nb_state_2: NotebookParser
):
    merged_state_with_diff = []
    for cell_state_1, cell_state_2 in zip(nb_state_1, nb_state_2):
        if cell_state_1 != cell_state_2:
            merged_state_with_diff.append((cell_state_1, cell_state_2))
    return merged_state_with_diff


def code_explain_change(
    nb_state_t_minus_1: NotebookParser,
    nb_state_t: NotebookParser
):
    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE_HEADER,
        input_variables=['nb_state_t_minus_1', 'nb_updates'],
        partial_variables={
            'NB_EXPLANATION_FORMAT': NB_CELLS_EXPLANATION_TEMPLATE,
        }
    )

    logger.trace(f'Code Explain Prompt:\n{prettify_str(prompt)}')
    llm = ChatOpenAI(model=GPT_MODEL_NAME, temperature=0.7)

    def parse(response):
        try:
            response = eval(response.content)
        except:
            try:
                response = parse_partial_json(response.content)
            except:
                raise Exception(f'Error, response is not a valid json:\n{response.content}')

        return response

    nb_updates = []
    for _, cell_state_t in get_diff_nb_states(
        nb_state_t_minus_1,
        nb_state_t
    ):
        nb_updates.append(cell_state_t.get_json())

    if len(nb_updates) == 0:
        raise Exception('No changes detected between the two notebook states')

    # print(json.dumps(nb_updates, indent=4))

    exp_parser = RunnableLambda(lambda x: parse(x))
    chain = prompt | llm | exp_parser
    diff_explain = chain.invoke({
        'nb_state_t_minus_1': str(nb_state_t_minus_1),
        'nb_updates': json.dumps(nb_updates, indent=4)
    })



    num_tokens_from_response = count_tokens_in_string(diff_explain)
    logger.trace(f'num_tokens from response: {num_tokens_from_response}')

    return diff_explain


