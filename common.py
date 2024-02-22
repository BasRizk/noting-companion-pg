import openai
from tabulate import tabulate
from nb_progress import NBStep
from parsers.nb_parser import CellEntry
from nb_progress import NotebookParser
from utils import (
    prettify_str,
    logger
)
from prompts.code_explain import code_explain_prompt
from prompts.generate_questions import make_questions_prompt

def generate_questions(prev_applied_changes_nb_states, explanations, prev_generated_questions):
    generated_questions = []
    for i in range(len(prev_applied_changes_nb_states)-1):
        print('><'*50)
        nb_state_i = prev_applied_changes_nb_states[i]
        nb_state_i_plus_1 = prev_applied_changes_nb_states[i+1]
        explanation_i = explanations[i]
        explanation_i_plus_1 = explanations[i+1]
        generated_questions.append(
            make_questions_prompt(
                nb_state_i, nb_state_i_plus_1,
                explanation_i, explanation_i_plus_1,
                prev_generated_questions + generated_questions
            )
        )
        # logger.trace(f'Generate Questions Prompt messages:\n{prettify_str(prompt)}')
        # generated_questions.append(call_llm(prompt))
        logger.trace(f'Generated Questions:\n {prettify_str(generated_questions[-1])}')
        print('><'*50)

    return generated_questions


def tabulate_aligned_msg_nb_cells(explanation, step: NBStep, change_i: int, nb_parser_with_change_applied: NotebookParser):
    from copy import deepcopy
    nb_cells_explanation = deepcopy(explanation['cells'])
    nb_summary = explanation['summary']


    # if change_i is not None:
    #     nb_cells_explanation[step.cell_id]['content'] = step.entries[change_i].get_formatted_content()
    #     nb_cells_explanation[step.cell_id]['action'] = step.get_change_type(change_i)


    table = [[
        'Cell ID', 'Assitant Msg', 'NB Cell'
    ]]
    for explanation_per_cell, nb_cell in zip(nb_cells_explanation, nb_parser_with_change_applied):
        nb_cell: CellEntry
        table.append([
            explanation_per_cell['cell_id'],
            prettify_str(explanation_per_cell, text_width=30),
            nb_cell.tabulate(text_width=50)
        ])

    table.append(['', '', ''])
    table.append(['Summary', prettify_str(nb_summary, text_width=30)])

    return tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")


def perform_explain_change_on_nb_parser(
    nb_parser_with_change_applied: NotebookParser,
    step: NBStep,
    step_i: int,
    prev_applied_changes_nb_states: list,
    prev_explanations: list,
    change_i: int=None,
    append_prev_msgs: bool=False
):
    # Use default prompt -- will be appended automatically by code_explain_prompt
    prev_msgs = []
    for prev_change, prev_response in zip(prev_applied_changes_nb_states, prev_explanations):
        prev_msgs.append({ "role": "user", "content": str(prev_change)})
        prev_msgs.append(prev_response)

    print('><'*50)
    if change_i is None:
        logger.warning(f'NB Step {step_i} @ cell #{step.cell_id}, No Change.')
    else:
        logger.debug(f'NB Step {step_i} Change({change_i}) {step.get_change_type(change_i)} @ cell #{step.cell_id}, '
                        f'Change Definition:\n{step.entries[change_i].tabulate()}')
    print('><'*50)

    while True:
        try:
            if append_prev_msgs:
                explanation = code_explain_prompt(nb_parser_with_change_applied, prev_messages=prev_msgs)
            else:
                explanation = code_explain_prompt(nb_parser_with_change_applied)
            break
        except openai.BadRequestError as e:
            if len(prev_msgs) > 0:
                logger.warning(f'Error, retrying with fewer prev_msgs: {len(prev_msgs)}')
                prev_msgs = prev_msgs[-1:]
            else:
                raise e

    prev_applied_changes_nb_states.append(nb_parser_with_change_applied)
    table = tabulate_aligned_msg_nb_cells(explanation, step, change_i, nb_parser_with_change_applied)

    if change_i is None:
        logger.info(f'NB Step {step_i} (Starter Code - No Change) Response:\n{table}')
    else:
        logger.info(f'NB Step {step_i} Change({change_i}) Response:\n {table}')

    return explanation