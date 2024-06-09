import os
from typing import List
from tqdm import tqdm
from parsers.nb_parser import NotebookParser
from parsers.log_parser import LogParser
from joblib import Parallel, delayed
from copy import deepcopy
from utils import (
    NotebookSession,
    get_selected_logged_sessions,
    get_selected_simulated_sessions,
    logger
)


def _generate_qa_pairs(
    nb_states: List[NotebookParser],
    t1: int, t2: int, method: str,
    consecutive_only: bool=True, # TODO, right now, consecutive_only is the only supported option
    num_questions: int=3
):
    from prompts.generate_questions_per_changes import make_questions_prompt
    from prompts.answer_questions_per_change import answer_questions

    nb_state_t1 = nb_states[t1]
    nb_state_t2 = nb_states[t2]

    qa_pairs_dict = {}
    nb_diffs = nb_state_t1.get_diff(nb_state_t2)
    if consecutive_only:
        if len(nb_diffs) != 1:
            breakpoint()
        assert len(nb_diffs) == 1, f'Expected 1 nb diffs, got {len(nb_diffs)}'
    else:
        raise NotImplementedError


    cell_before_modification = nb_diffs[0][0]
    cell_after_modification = nb_diffs[0][1]
    # code_before_modification = '\n'.join(cell_before_modification.source)
    code_after_modification = '\n'.join(cell_after_modification.source)
    code_out =\
        f'**Before Modification**\n' +\
        f'{cell_before_modification.get_xml()}\n' +\
        f'**After Modification**\n' +\
        f'{cell_after_modification.get_xml()}'

    if method == 'offline':
        questions = make_questions_prompt(
            nb_state_t1,
            nb_state_t2,
            max_num_questions_per_update=num_questions,
        )
        answers, t1_contexts, t2_contexts = answer_questions(
            nb_state_t1,
            nb_state_t2,
            questions,
        )
        question_answers = [
            {
                'question': question,
                'answer': answer,
                't1_context': t1_context,
                't2_context': t2_context
            }
            for question, answer, t1_context, t2_context
            in zip(questions, answers, t1_contexts, t2_contexts)
        ]
        qa_pairs_dict[(t1, t2)] = {'code': code_out, 'question_answers': question_answers}

    elif method == 'online':
        import requests
        response_json = requests.post('https://ckg12.isi.edu/knic-services/generate_questions', json={
            'code': code_after_modification,
            'num_questions': num_questions
        }).json()['results']
        assert response_json['code'] == code_after_modification, f'Expected code to be the same, got {qa_pairs_dict[(t1, t2)]["code"]}'
        question_answers = [
            {
                'question': qa['question'],
                'answer': qa['answer']
            }
            for qa in response_json['question_answers']
        ]
        qa_pairs_dict[(t1, t2)] = {'code': code_out, 'question_answers': question_answers}

    elif method == 'mix':
        # generate questions from online method
        # generate answers from offline method
        qa_pairs_dict = _generate_qa_pairs(
            nb_states, t1, t2, consecutive_only=True,
            method='online', num_questions=num_questions
        )
        assert code_out == qa_pairs_dict[(t1, t2)]['code'], f'Expected code to be the same, got {qa_pairs_dict[(t1, t2)]["code"]}'
        # online generated questions
        questions = [
            qa['question']
            for qa in qa_pairs_dict[(t1, t2)]['question_answers']
        ]
        # answer questions from online method using offline method answering part
        offline_answers, t1_contexts, t2_contexts = answer_questions(
            nb_state_t1,
            nb_state_t2,
            questions,
        )
        question_answers = [
            {
                'question': question,
                'answer_online': online_qa['answer'],
                'answer_offline': offline_answer,
                't1_context': t1_context,
                't2_context': t2_context
            }
            for question, offline_answer, t1_context, t2_context, online_qa in zip(
                questions,
                offline_answers, t1_contexts, t2_contexts,
                qa_pairs_dict[(t1, t2)]['question_answers']
            )
        ]
        qa_pairs_dict[(t1, t2)] = {'code': code_out, 'question_answers': question_answers}
    else:
        raise ValueError(f'Invalid method: {method}')

    return qa_pairs_dict

def get_qa_pairs(
    nb_states: List[NotebookParser],
    consecutive_only=True, method='offline',
    num_questions=3, pbar=True, n_jobs=-1
):
    qa_pairs_dict = {}
    for i in range(len(nb_states)):
        for j in range(i+1, len(nb_states)):
            if consecutive_only and j != i + 1:
                continue
            qa_pairs_dict[(i, j)] = None

    with tqdm(
        total=len(qa_pairs_dict),
        desc=f'Generating QA pairs using {method}',
        disable=not pbar
    ) as _pbar:
        for i, sub_qa_pairs_dict in enumerate(Parallel(
            n_jobs=n_jobs, return_as='generator',
        )(
            delayed(_generate_qa_pairs)(
                nb_states, t1, t2, method,
                consecutive_only=consecutive_only,
                num_questions=num_questions
            )
            for (t1, t2) in qa_pairs_dict.keys()
        )):
            print(i)
            print('='*100)
            qa_pairs_dict.update(sub_qa_pairs_dict)
            _pbar.update(1)

    return qa_pairs_dict



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebooks_dir', type=str, default='data/tac_notebooks')
    parser.add_argument('--logs_dir', type=str, default='data/tac_raw_logs')
    parser.add_argument('--simulate_log', action='store_true', default=False)
    parser.add_argument('--min_num_steps', type=int, default=4, help='Minimum number of steps in the progress log to consider a session')
    parser.add_argument('--keep_code_header_comments', action='store_true', default=False)
    parser.add_argument('--output_dir', type=str, default='generated_qa_pairs')
    parser.add_argument('--n_jobs', type=int, default=-1)
    parser.add_argument('--num_questions', type=int, default=3)
    parser.add_argument('--offset', type=float, default=0,
                        help='Offset for the first step in notebook progress to start generating QA pairs')
    parser.add_argument(
        '--methods', nargs='+',
        default=[
            'offline',
            # 'online',
            'mix'
        ],
        choices=['offline', 'online', 'mix']
    )
    parser.add_argument('--shuffle_methods', action='store_true', default=False)
    args = parser.parse_args()

    if not os.path.exists(args.logs_dir) and not args.simulate_log:
        raise ValueError(f'Invalid logs_dir: {args.logs_dir}, while simulate_log is False')

    if args.simulate_log:
        logger.info('Simulating logs')

    args.output_dir = os.path.join(
        args.output_dir,
        args.notebooks_dir.replace('/', '_'),
        '_'.join(sorted(args.methods))
    )

    os.makedirs(args.output_dir, exist_ok=True)


    if args.simulate_log:
        selected_sessions: List[NotebookSession] = get_selected_simulated_sessions(
            args.notebooks_dir, min_num_steps=args.min_num_steps, offset=args.offset,
        )
    else:
        selected_sessions: List[NotebookSession] = get_selected_logged_sessions(
            args.notebooks_dir, args.logs_dir,
            min_num_steps=args.min_num_steps, offset=args.offset
        )

    for nb_session in selected_sessions:
        nb_session.info()
        qa_pairs_from_methods = [
            (
                method,
                get_qa_pairs(
                    deepcopy(nb_session.nb_states),
                    consecutive_only=True,
                    method=method,
                    num_questions=args.num_questions,
                    n_jobs=args.n_jobs,
                )
            ) for method in args.methods
        ]

        if args.shuffle_methods:
            import random
            random.shuffle(qa_pairs_from_methods)


        # write excel file with maximum width for each column
        import xlsxwriter
        csv_filename = f'{args.output_dir}/qa_pairs_{nb_session.name}.xlsx'
        workbook = xlsxwriter.Workbook(csv_filename)
        worksheet = workbook.add_worksheet()
        width = 45
        # worksheet.set_column('A:A', width)
        worksheet.write('A1', 'step_num')
        worksheet.set_column('B:B', width)
        worksheet.write('B1', 'modified_code')
        col_offset_start = 2
        col_offset = col_offset_start
        for method, qa_pairs in qa_pairs_from_methods:
            qa_pairs_method_name = f'{method}_qa_pairs'
            some_qa_pairs = list(qa_pairs.values())[0]
            qa = list(some_qa_pairs['question_answers'])[1]
            for i, (k, v) in enumerate(qa.items()):
                col_id = chr(ord('A') + i + col_offset)
                worksheet.set_column(f'{col_id}:{col_id}', width)
                worksheet.write(f'{col_id}1', f'{k}_{qa_pairs_method_name}')
            col_offset += 2
        wrap_format = workbook.add_format({'text_wrap': True})

        if 1 > args.offset > 0:
            step_num_offset = int(len(qa_pairs_from_methods[0][1])/args.offset)
        else:
            if int(args.offset) != args.offset:
                raise ValueError(f'Invalid offset: {args.offset}')
            step_num_offset = int(args.offset)

        row = 1
        for step_num, (t1, t2) in enumerate(qa_pairs_from_methods[0][1].keys(), step_num_offset):
            col_offset = col_offset_start
            for method, qa_pairs in qa_pairs_from_methods:
                qa_pairs_method_name = f'{method}_qa_pairs'
                qa_pair = qa_pairs[(t1, t2)]
                worksheet.write(row, 0, step_num) # NOTE: rewritten for each method; should be same
                worksheet.write(row, 1, qa_pair['code'], wrap_format) # NOTE: rewritten for each method; should be same
                for row_offset, qa in enumerate(qa_pair['question_answers']):
                    for i, (k, v) in enumerate(qa.items()):
                        worksheet.write(row + row_offset, i + col_offset, v, wrap_format)
                col_offset += 2
            row += len(qa_pair['question_answers']) + 1
        workbook.close()

        logger.info(f'Wrote to {csv_filename}')

        # # write text file including which method correspond to which column
        # txt_filename = f'{args.output_dir}/qa_pairs_{nb_session.name}.txt'
        # with open(txt_filename, mode='w') as txt_file:
        #     txt_file.write(f'Column 1: modified_code\n')
        #     # txt_file.write(f'Column 2: question_{qa_pairs_method_1_method_name}\n')
        #     # txt_file.write(f'Column 3: answer_{qa_pairs_method_1_method_name}\n')
        #     # txt_file.write(f'Column 4: question_{qa_pairs_method_2_method_name}\n')
        #     # txt_file.write(f'Column 5: answer_{qa_pairs_method_2_method_name}\n')
        #     for i, (method, _) in enumerate(qa_pairs_from_methods):
        #         qa_pairs_method_name = f'{method}_qa_pairs'
        #         txt_file.write(f'Column {i+2}: question_{qa_pairs_method_name}\n')
        #         txt_file.write(f'Column {i+3}: answer_{qa_pairs_method_name}\n')

        nb_session.write_first_last_states(args.output_dir)
