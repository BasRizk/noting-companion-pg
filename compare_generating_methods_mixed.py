import os
from loguru import logger
from typing import List
from parsers.nb_parser import NotebookParser
from parsers.log_parser import LogParser
from utils import get_all_file_with_extension_in_dir_recursively, logger

def get_qa_pairs(nb_states, consecutive_only=True, method='offline', num_questions=3):
    from prompts.generate_questions_per_changes import make_questions_prompt
    from prompts.answer_questions_per_change import answer_questions
    from prompts.code_explain_change import get_diff_nb_states

    qa_pairs_dict = {}
    for i in range(len(nb_states)):
        for j in range(i+1, len(nb_states)):
            if consecutive_only and j != i + 1:
                continue
            qa_pairs_dict[(i, j)] = None

    for (t1, t2) in qa_pairs_dict.keys():
        cell_diff = get_diff_nb_states(nb_states[t1], nb_states[t2])
        if consecutive_only:
            if len(cell_diff) != 1:
                breakpoint()
            assert len(cell_diff) == 1, f'Expected 1 cell diff, got {len(cell_diff)}'
        else:
            raise NotImplementedError

        code_before_modification = '\n'.join(cell_diff[0][0].get_json()['source'])
        code_after_modification = '\n'.join(cell_diff[0][1].get_json()['source'])

        if method == 'offline':
            questions = make_questions_prompt(
                nb_states[t1],
                nb_states[t2],
                max_num_questions_per_update=num_questions,
                # changes_exps_dict[(t1, t2)] # TODO try to use this as hints
            )
            answers, _, _ = answer_questions(
                nb_states[t1],
                nb_states[t2],
                questions,
            )
            question_answers = [
                {
                    'question': question,
                    'answer': answer
                }
                for question, answer in zip(questions, answers)
            ]
            qa_pairs_dict[(t1, t2)] = {
                'code': f'> Before Modification\n{code_before_modification}\n\n > After Modification\n{code_after_modification}',
                'question_answers': question_answers
            }

        elif method == 'online':
            import requests
            # make request to `https://ckg12.isi.edu/knic-services/generate_questions`
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
            qa_pairs_dict[(t1, t2)] = {
                'code': f'> Before Modification\n{code_before_modification}\n\n > After Modification\n{code_after_modification}',
                'question_answers': question_answers
            }

        elif method == 'mix':
            # generate questions from online method
            # generate answers from offline method
            qa_pairs_dict = get_qa_pairs(nb_states, consecutive_only=True, method='online')
            for (t1, t2) in qa_pairs_dict.keys():
                cell_diff = get_diff_nb_states(nb_states[t1], nb_states[t2])
                assert len(cell_diff) == 1, f'Expected 1 cell diff, got {len(cell_diff)}'
                code_before_modification = '\n'.join(cell_diff[0][0].get_json()['source'])
                code_after_modification = '\n'.join(cell_diff[0][1].get_json()['source'])
                code_out = f'> Before Modification\n{code_before_modification}\n\n > After Modification\n{code_after_modification}'
                assert code_out == qa_pairs_dict[(t1, t2)]['code'], f'Expected code to be the same, got {qa_pairs_dict[(t1, t2)]["code"]}'
                # online generated questions
                questions = [
                    qa['question']
                    for qa in qa_pairs_dict[(t1, t2)]['question_answers']
                ]
                # answer questions from online method using offline method answering part
                answers, _, _ = answer_questions(
                    nb_states[t1],
                    nb_states[t2],
                    questions,
                )
                question_answers = [
                    {
                        'question': question,
                        'answer_offline': offline_answer,
                        'answer_online': online_qa['answer']
                    }
                    for question, offline_answer, online_qa in zip(questions, answers, qa_pairs_dict[(t1, t2)]['question_answers'])
                ]
                qa_pairs_dict[(t1, t2)] = {
                    'code': f'> Before Modification\n{code_before_modification}\n\n > After Modification\n{code_after_modification}',
                    'question_answers': question_answers
                }
        else:
            raise ValueError(f'Invalid method: {method}')

    return qa_pairs_dict



if __name__ == "__main__":
    notebooks_dir = 'data/tac_notebooks'
    logs_dir = 'data/tac_raw_logs'
    all_log_filepathes = get_all_file_with_extension_in_dir_recursively(logs_dir, ".log")
    all_log_filepathes.sort()
    # skip files containing baseline
    all_log_filepathes = [log_filepath for log_filepath in all_log_filepathes if "baseline" not in log_filepath]
    logger.success(f'There are {len(all_log_filepathes)} log files in {logs_dir} directory')

    selected_sessions = []
    for selected_log_filepath in all_log_filepathes:
        log_parser = LogParser(selected_log_filepath).parse()
        nb_sublog_dict = log_parser.attach_notebooks(notebooks_dir, verbose=False)
        # logger.debug(
        #     'Sample:' +\
        #     f'\nSelected log file: {selected_log_filepath}' +\
        #     f'\nfetching notebooks from log file: {notebooks_dir}' +\
        #     f'\nLog parser per these notebooks:\n{nb_sublog_dict.keys()}'
        # )

        from nb_progress import get_notebook_progress_using_log, InvalidLogError, NotebookStateLogMismatchError


        for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(nb_sublog_dict.items()):
            try:
                nb_progress = get_notebook_progress_using_log(nb_parser, nb_log_parser)
            except InvalidLogError as e:
                # logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
                continue
            except NotebookStateLogMismatchError as e:
                # logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
                continue


            nb_states: List[NotebookParser] = []
            for step_i, step in enumerate(nb_progress):
                step.reset()
                if len(step) == 0:
                    nb_states.append(step.nb_parser_state)
                else:
                    # prev_msgs = [] # TODO should I reset prev_msgs upon each completed step?
                    for change_i, nb_parser_with_change_applied in enumerate(step):
                        nb_states.append(
                            nb_parser_with_change_applied
                        )

            num_progress_steps = len(nb_progress)

            if num_progress_steps >= 4:
                # logger.info(f'Notebook: {nb_parser.filepath}')
                # logger.info(f'Log: {nb_log_parser.filepath}')
                # logger.info(f'Number of progress steps: {num_progress_steps}')
                selected_sessions.append((nb_parser, nb_log_parser, nb_progress, nb_states))




    output_dir = 'data/qa_pairs'
    os.makedirs(output_dir, exist_ok=True)

    for nb_parser, nb_log_parser, nb_progress, nb_states in selected_sessions:
        logger.info(f'Notebook: {nb_parser.filepath}')
        logger.info(f'Log: {nb_log_parser.filepath}')
        logger.info(f'Number of progress steps: {len(nb_progress)}')

        qa_pairs_mixed = get_qa_pairs(nb_states, consecutive_only=True, method='mix')
        csv_filename = f'{output_dir}/qa_pairs_{nb_parser.filepath.replace("/", "_")}_{nb_log_parser.filepath.replace("/", "_")}.xlsx'

        # write excel file with maximum width for each column
        import xlsxwriter
        workbook = xlsxwriter.Workbook(csv_filename)
        worksheet = workbook.add_worksheet()
        width = 45
        worksheet.set_column('A:A', width)
        worksheet.set_column('B:B', width)
        worksheet.set_column('C:C', width)
        worksheet.set_column('D:D', width)
        worksheet.write('A1', 'code')
        worksheet.write('B1', f'question')
        worksheet.write('C1', f'answer_offline')
        worksheet.write('D1', f'answer_online')

        # wrap text
        wrap_format = workbook.add_format({'text_wrap': True})

        row = 1
        for (t1, t2) in qa_pairs_mixed.keys():
            qa_pair = qa_pairs_mixed[(t1, t2)]
            worksheet.write(f'A{row}', qa_pair['code'], wrap_format)
            for i, qa in enumerate(qa_pair['question_answers']):
                worksheet.write(f'B{row+i}', qa['question'], wrap_format)
                worksheet.write(f'C{row+i}', qa['answer_offline'], wrap_format)
                worksheet.write(f'D{row+i}', qa['answer_online'], wrap_format)
            row += len(qa_pair['question_answers']) + 1
        workbook.close()

        # write notebook first and last states
        first_state = nb_states[0]
        last_state = nb_states[-1]
        qa_states_dir= f'{output_dir}/qa_pairs_{nb_parser.filepath.replace("/", "_")}_{nb_log_parser.filepath.replace("/", "_")}'
        os.makedirs(qa_states_dir, exist_ok=True)
        first_state.to_notebook(directory=qa_states_dir, filepath_postfix='_first_state')
        last_state.to_notebook(directory=qa_states_dir, filepath_postfix='_last_state')
        logger.info(f'Wrote to {qa_states_dir} the method names for each column in the csv file')
