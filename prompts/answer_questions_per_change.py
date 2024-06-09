from typing import List, Tuple
from operator import itemgetter
from langchain_core.output_parsers import (
    JsonOutputParser,
    StrOutputParser
)
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
# from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from . import GPT_MODEL_NAME
# from utils import prettify_str, logger
from parsers.nb_parser import NotebookParser, CellEntry

# model = OpenAI(
#     model='gpt-3.5-turbo-instruct',
#     temperature=0.9
# )

def _create_nb_retriever(
    nb_state: NotebookParser,
    collection_name: str,
    exclude_ids: List[str] = []
):
    from langchain.storage import InMemoryByteStore
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings
    from langchain.retrievers.multi_vector import MultiVectorRetriever

    # NOTE: filter out empty cells and cells that are not of interest (exclude_ids)
    cells_of_interest = [
        cell for cell in nb_state.get_cells()
        if cell['source'] and cell['id'] not in exclude_ids
    ]


    nb_state_docs = [
        Document(
            page_content=str(cell['source']),
            metadata={"id": cell['id'], "cell_type": cell['cell_type']}
        ) for cell in cells_of_interest
    ]

    # nb_vectorstore = FAISS.from_documents(
    #     nb_state_docs,
    #     embedding=OpenAIEmbeddings(),
    #     normalize_L2=False,
    #     distance_strategy=DistanceStrategy.COSINE
    # )
    # return nb_vectorstore

    nb_vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=OpenAIEmbeddings()
    )

    # The storage layer for the parent docments
    store = InMemoryByteStore()
    # The retriever (empty to start)
    nb_cells_retriever = MultiVectorRetriever(
        vectorstore=nb_vectorstore,
        byte_store=store,
        id_key='id',
    )
    cell_line_level_docs = []
    for cell in cells_of_interest:
        _sub_docs = [
            Document(
                page_content=line,
                metadata={"id": cell['id'], "cell_type": cell['cell_type']}
            )
            for line in cell['source']
        ]
        cell_line_level_docs.extend(_sub_docs)

    doc_ids = [doc.metadata['id'] for doc in nb_state_docs]
    nb_cells_retriever.vectorstore.add_documents(cell_line_level_docs)
    nb_cells_retriever.docstore.mset(list(zip(doc_ids, nb_state_docs)))

    return nb_cells_retriever

def answer_questions(
    nb_state_t1: NotebookParser,
    nb_state_t2: NotebookParser,
    questions: List[str],
    # change_explanation: str = None,
):
    # TODO filter out the updated cells from the vectorstores by retriever
    nb_updates: List[Tuple[CellEntry, CellEntry]] = nb_state_t1.get_updates(nb_state_t2)
    nb_updates_ids = [nb_update.cell_id for nb_update in nb_updates]
    # nb_ids = [cell['id'] for cell in nb_state_t_minus_1.get_cells()]
    # nb_ids_not_updated = [nb_id for nb_id in nb_ids if nb_id not in nb_updates_ids]

    nb_t1_cells_retriever = _create_nb_retriever(nb_state_t1, 'nb_state_t1', exclude_ids=nb_updates_ids)
    nb_t2_cells_retriever = _create_nb_retriever(nb_state_t2, 'nb_state_t2', exclude_ids=nb_updates_ids)

    def _format_context(nb_cell_docs):
        # sort the cells by their original order in the notebook
        nb_cell_docs = sorted(nb_cell_docs, key=lambda doc: doc.metadata['id'])
        nb_cells_strs = []
        for nb_cell_doc in nb_cell_docs:
            cell_entry = CellEntry(
                cell_type=nb_cell_doc.metadata['cell_type'],
                cell_id=nb_cell_doc.metadata['id'],
                source=eval(nb_cell_doc.page_content) # NOTE: eval here is applied over a string/line of code (not a list of strings/lines of code)
            )
            nb_cells_strs.append(cell_entry.get_xml())

        return "\n".join(nb_cells_strs)

    context_chain = RunnableParallel(
        context_t1=itemgetter("question") | nb_t1_cells_retriever | _format_context,
        context_t2=itemgetter("question") | nb_t2_cells_retriever | _format_context,
        question=itemgetter("question"),
        nb_updates=itemgetter("nb_updates"),
    )

    prompt = ChatPromptTemplate.from_template("""
        Answer the question based only on the following (If answers cannot be made given the context and this particular step in the notebook, please indicate so):

        <most_relevant_cells_from_python_notebook_at_time_t1>
        {context_t1}
        </most_relevant_cells_from_python_notebook_at_time_t1>

        <most_relevant_cells_from_python_notebook_at_time_t2>
        {context_t2}
        </most_relevant_cells_from_python_notebook_at_time_t2>

        <recent_notebook_updates>
        {nb_updates}
        </recent_notebook_updates>

        Question: {question}
        """
    )
    model = ChatOpenAI(model=GPT_MODEL_NAME, temperature=0.5)
    generate_answers_chain =(
        prompt
        | model
        | StrOutputParser()
    )

    combined_chain = (
        context_chain
        | RunnableParallel(
            answers=generate_answers_chain,
            inputs=RunnablePassthrough()
        )
    )


    responses = combined_chain.batch(
        [
            {
                "nb_updates": '\n\n'.join([
                    cell.get_xml() for cell in nb_updates
                ]),
                "question": question,
            } for question in questions
        ]
    )
    answers = [res['answers'] for res in responses]
    contexts_1 = [res['inputs']['context_t1'] for res in responses]
    contexts_2 = [res['inputs']['context_t2'] for res in responses]
    return answers, contexts_1, contexts_2