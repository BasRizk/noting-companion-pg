import json
from typing import List, Tuple
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

from parsers.nb_parser import NotebookParser
from operator import itemgetter

from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAI, OpenAIEmbeddings


def answer_questions(
    nb_state_t_minus_1: NotebookParser,
    nb_state_t: NotebookParser,
    questions: List[str],
    # change_explanation: str = None,
):
    # nb_updates = _get_nb_states_updates(
    #     nb_state_t_minus_1,
    #     nb_state_t
    # )

    retriever_t1 = FAISS.from_texts(
        list(map(str, nb_state_t_minus_1.get_cells())),
        embedding=OpenAIEmbeddings()
    ).as_retriever()

    retriever_t2 = FAISS.from_texts(
        list(map(str, nb_state_t.get_cells())),
        embedding=OpenAIEmbeddings()
    ).as_retriever()

    template = """Answer the question based only on the following:

    relevant context from python notebook at time t1:
    {context_t1}

    relevant context from python notebook at time t2:
    {context_t2}

    Question: {question}
    """
    prompt = ChatPromptTemplate.from_template(template)


    model = ChatOpenAI(
        model=GPT_MODEL_NAME,
        temperature=0.9
    )
    # model = OpenAI(
    #     model='gpt-3.5-turbo-instruct',
    #     temperature=0.9
    # )
    import re
    chain = (
        {
            "context_t1": itemgetter("question") | retriever_t1,
            "context_t2": itemgetter("question") | retriever_t2,
            "question": itemgetter("question"),
        }
        | prompt
        | model
        | StrOutputParser()
        | RunnablePassthrough(lambda x: re.sub(r'Answer+.', '', x, 1).strip())
    )

    answers = []
    for question in questions:
        answers.append(
            chain.invoke({
                "question": question,
            })
        )
    return answers, retriever_t1, retriever_t2