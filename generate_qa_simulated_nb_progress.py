import os
import argparse
from utils import get_selected_simulated_sessions, logger
from  compare_generating_methods_mixed import get_qa_pairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebooks_dir', type=str, default='data/tac_notebooks')
    parser.add_argument('--keep_code_header_comments', action='store_true', default=False)
    parser.add_argument('--output_dir', type=str, default='data/qa_pairs')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    selected_sessions = get_selected_simulated_sessions(args.notebooks_dir, min_num_steps=4)

    for nb_parser, nb_progress, nb_states in selected_sessions:
        qa_pairs_mixed = get_qa_pairs(nb_states, consecutive_only=True, method='offline', num_questions=3)

        # Save the qa_pairs to a file
        csv_filename = f'{args.output_dir}/qa_pairs_{nb_parser.filepath.replace("/", "_")}_simulated_progress.xlsx'

        import xlsxwriter
        workbook = xlsxwriter.Workbook(csv_filename)
        worksheet = workbook.add_worksheet()
        width = 45
        worksheet.set_column('A:A', width)
        worksheet.set_column('B:B', width)
        worksheet.set_column('C:C', width)
        worksheet.write('A1', 'code')
        worksheet.write('B1', f'question')
        worksheet.write('C1', f'answer_offline')

        # wrap text
        wrap_format = workbook.add_format({'text_wrap': True})

        row = 1
        for (t1, t2) in qa_pairs_mixed.keys():
            qa_pair = qa_pairs_mixed[(t1, t2)]
            worksheet.write(f'A{row}', qa_pair['code'], wrap_format)
            for i, qa in enumerate(qa_pair['question_answers']):
                worksheet.write(f'B{row+i}', qa['question'], wrap_format)
                worksheet.write(f'C{row+i}', qa['answer'], wrap_format)
            row += len(qa_pair['question_answers']) + 1
        workbook.close()

        logger.info(f"Saved qa_pairs to {csv_filename}")